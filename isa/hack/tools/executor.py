from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

try:
    from .assembler import (
        COMMENT_LEVELS,
        AssemblyError,
        Assertion,
        LoadedHack,
        apply_runtime_overrides,
        assemble,
        load_hack,
        normalize_hook_path,
        validate_comment_level,
        write_hack,
    )
except ImportError:  # Direct execution: python isa/hack/tools/executor.py
    from assembler import (
        COMMENT_LEVELS,
        AssemblyError,
        Assertion,
        LoadedHack,
        apply_runtime_overrides,
        assemble,
        load_hack,
        normalize_hook_path,
        validate_comment_level,
        write_hack,
    )

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
ROOT = PACKAGE_ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools import install_sail

ISA_SOURCE = PACKAGE_ROOT / "hack.sail"
COMPAT_HEADER = ROOT / "support/sail_windows_compat.h"
COMPAT_SOURCE = ROOT / "support/sail_windows_compat.c"
DEFAULT_MAX_STEPS = 100_000


def command(args: list[str]) -> None:
    _ = subprocess.run(args, cwd=ROOT, check=True)


def artifact(prefix: Path, suffix: str) -> Path:
    return Path(f"{prefix}{suffix}")


def resolve_hook_source(hook_path: str) -> Path:
    try:
        normalized = normalize_hook_path(hook_path)
    except ValueError as error:
        raise ValueError(f"invalid selected hook path {hook_path!r}: {error}") from error
    if hook_path != normalized:
        raise ValueError("selected hook path must be normalized POSIX")

    candidate = PACKAGE_ROOT.joinpath(*PurePosixPath(normalized).parts)
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as error:
        raise OSError(f"selected hook source does not exist: {hook_path}") from error
    try:
        resolved.relative_to(PACKAGE_ROOT.resolve())
    except ValueError as error:
        raise ValueError(f"selected hook source escapes isa/hack: {hook_path}") from error
    if not resolved.is_file():
        raise OSError(f"selected hook source is not a file: {hook_path}")
    return resolved


def remove_artifact(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        if os.name != "nt" or not (username := os.environ.get("USERNAME")):
            raise
        command(["icacls", str(path), "/grant", f"{username}:(F)"])
        path.unlink(missing_ok=True)


def _assertion_location(target: str) -> str:
    if target.startswith("R") and target[1:].isdigit():
        return f"RAM[{int(target[1:])}]"
    return target


def _assertion_expression(assertion: Assertion) -> str:
    location = _assertion_location(assertion.target)
    if assertion.operator in {"==", "!="}:
        literal = f"0b{assertion.value:015b}" if assertion.target == "PC" else f"0x{assertion.value:04X}"
        return f"{location} {assertion.operator} {literal}"
    return f"{assertion.mode}({location}) {assertion.operator} {assertion.value}"


def _assertion_source(assertion: Assertion) -> str:
    target = assertion.target
    if target != "PC" and assertion.mode in {"signed", "unsigned"}:
        target = f"{assertion.mode}({target})"
    if assertion.operator in {"==", "!="}:
        value = f"0b{assertion.value:015b}" if assertion.target == "PC" else f"0x{assertion.value:04X}"
    else:
        value = str(assertion.value)
    return f"{target} {assertion.operator} {value}"


def write_driver(
    program: LoadedHack,
    max_steps: int | None,
    path: Path,
    binary: Path,
    comments: str = "summary",
    bounded_snapshot: bool = False,
) -> None:
    comments = validate_comment_level(comments)
    words = program.words
    metadata = program.metadata
    if bounded_snapshot and (
        max_steps is None or metadata.halt_addresses or not metadata.assertions
    ):
        raise ValueError("bounded snapshot requires max_steps, assertions, and no lowered HALT")

    load_lines: list[str] = []
    for address, word in enumerate(words):
        suffix = ""
        if comments != "none":
            source = program.word_comments[address] if address < len(program.word_comments) else None
            annotation = source or f"ROM[{address:04d}]"
            suffix = f" // {annotation}"
        load_lines.append(f"  ROM[{address}] = 0b{word:016b};{suffix}")
    loads = "\n".join(load_lines)
    halt_lines: list[str] = []
    for index, address in enumerate(metadata.halt_addresses):
        suffix = "" if comments == "none" else (
            f" // Lowered HALT metadata at ROM[{address:04d}]; not an ISA encoding."
        )
        halt_lines.append(
            f"let lowered_halt_{index} : program_counter = 0b{address:015b}{suffix}"
        )
    halt_values = "" if not halt_lines else "\n".join(halt_lines) + "\n"
    not_halted_condition = " & ".join(
        f"(pc != lowered_halt_{index})" for index in range(len(metadata.halt_addresses))
    )
    halted_condition = " | ".join(
        f"PC == lowered_halt_{index}" for index in range(len(metadata.halt_addresses))
    ) or "false"
    pending_condition = "unsigned(pc) < loaded_rom_words"
    if not_halted_condition:
        pending_condition = f"{not_halted_condition} & {pending_condition}"

    assertion_lines: list[str] = []
    for assertion in metadata.assertions:
        if comments == "full":
            assertion_lines.append(
                f"  // Source line {assertion.line}: .assert {_assertion_source(assertion)}"
            )
        assertion_lines.append(
            f'  assert ({_assertion_expression(assertion)}, "assertion {_assertion_source(assertion)} from source line {assertion.line} failed");'
        )
    assertions = "\n".join(assertion_lines)
    status = "ASSERT PASS" if metadata.assertions else "RUN COMPLETE"

    inline_step_doc = "" if comments == "none" else (
        "    // Check the model-owned fetch, decode, and execute outcome.\n"
    )
    step_body = f"""    hack_hook_before_step(steps);
{inline_step_doc}    match hack_step() {{
      HackRetired(()) => (),
      HackIllegalInstruction(_) => assert(false, "illegal Hack instruction encoding")
    }};
    steps = steps + 1;
    hack_hook_after_step(steps)"""
    continue_condition = pending_condition
    if max_steps is None:
        limit_check = ""
    else:
        continue_condition = f"{pending_condition} & steps < driver_max_steps"
        if bounded_snapshot:
            limit_check = ""
        elif metadata.halt_addresses:
            limit_check = (
                f'  assert ({halted_condition}, "maximum step limit reached before lowered HALT");\n'
            )
        else:
            limit_check = (
                '  assert (false, "maximum step limit reached without lowered HALT or an explicit bounded snapshot");\n'
            )
    loop = f"""  while execution_should_continue(PC, steps) {{
{step_body}
  }};"""

    header = "" if comments == "none" else (
        f"// Generated by executor.py from {binary.name}; regenerate instead of editing.\n"
    )
    size_doc = "" if comments == "none" else (
        "// Loaded artifact size, not an execution step limit.\n"
    )
    step_limit = "" if max_steps is None else f"let driver_max_steps : int = {max_steps}\n"
    load_doc = "" if comments == "none" else (
        "// Load raw machine words into the model-owned ROM before execution.\n"
    )
    continue_doc = "" if comments == "none" else (
        "// Return whether another instruction attempt may begin; this does not declare successful completion.\n"
    )
    main_doc = "" if comments == "none" else (
        "// Load the ROM, run while another attempt is allowed, then validate why execution stopped.\n"
    )
    before_run_doc = "" if comments != "full" else (
        "  // Hooks share this process and observe the same A, D, PC, and RAM state.\n"
    )
    after_loop_doc = "" if comments != "full" else (
        "  // Distinguish valid HALT/bounded completion from leaving the loaded image or watchdog failure.\n"
    )
    output_doc = "" if comments != "full" else (
        "  // This dump is diagnostic; Sail assertions and exit status determine success.\n"
    )

    path.write_text(
        f"""{header}{size_doc}let loaded_rom_words : int = {len(words)}
{step_limit}{halt_values}
{load_doc}function load_program() -> unit = {{
{loads}
  ()
}}

{continue_doc}function execution_should_continue(pc : program_counter, steps : int) -> bool = {{
  {continue_condition}
}}

{main_doc}function main() -> unit = {{
  var steps : int = 0;
  load_program();
{before_run_doc}  hack_hook_before_run();
{loop}
{after_loop_doc}  assert (unsigned(PC) < loaded_rom_words, "program counter left the loaded ROM image");
{limit_check}{assertions}
  hack_hook_after_run(steps);
{output_doc}  print_endline("{status}");
  print_bits("A  = ", A);
  print_bits("D  = ", D);
  print_bits("PC = ", PC);
  print_bits("R0 = ", RAM[0]);
  print_bits("R1 = ", RAM[1]);
  print_bits("R2 = ", RAM[2]);
  print_bits("R3 = ", RAM[3]);
  print_bits("R4 = ", RAM[4]);
  print_bits("R5 = ", RAM[5]);
  print_bits("R6 = ", RAM[6]);
  print_bits("R7 = ", RAM[7])
}}
""",
        encoding="utf-8",
    )


def c_compiler() -> str:
    if os.name == "nt":
        return "x86_64-w64-mingw32-gcc"
    if sys.platform.startswith("linux"):
        return "gcc"
    raise OSError(f"unsupported C compiler platform: {sys.platform}")


def compile_and_run(output: Path, driver: Path, hook_source: Path) -> None:
    sail = install_sail.ensure_installed()
    sail_root = sail.parent.parent
    command([str(sail), "-c", "-o", str(output), str(ISA_SOURCE), str(hook_source), str(driver)])

    sail_lib = sail_root / "share/sail/lib"
    if not sail_lib.is_dir():
        raise OSError(f"Sail C runtime not found: {sail_lib}")
    compiler = c_compiler()
    executable = artifact(output, ".exe") if os.name == "nt" else output
    args = [
        compiler, "-include", str(COMPAT_HEADER), f"-I{sail_lib}", "-o", str(executable),
        str(artifact(output, ".c")),
        *[str(sail_lib / f"{name}.c") for name in ("rts", "elf", "sail", "sail_config", "sail_failure", "cJSON")],
        str(COMPAT_SOURCE), "-lgmp",
    ]
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if os.name == "nt":
        if conda_prefix is None:
            raise OSError("CONDA_PREFIX is required to locate GMP on Windows")
        conda = Path(conda_prefix)
        args[4:4] = [f"-I{conda / 'Library/include'}", f"-L{conda / 'Library/lib'}"]
    elif conda_prefix is not None:
        conda = Path(conda_prefix)
        args[4:4] = [f"-I{conda / 'include'}", f"-L{conda / 'lib'}"]
    command(args)
    command([str(executable)])


def run(
    program: Path,
    output: Path,
    max_steps: int | None = None,
    hook: str | None = None,
    require_assertions: bool = False,
    comments: str = "summary",
) -> None:
    comments = validate_comment_level(comments)
    if max_steps is not None and max_steps <= 0:
        raise ValueError("--max-steps must be a positive integer")
    if output.name in {"", ".", ".."}:
        raise ValueError("--output must be a file prefix")

    assembly = assemble(program)
    if len(assembly.records) > 32768:
        raise ValueError("program exceeds the 32768-word Hack ROM")
    assembly = apply_runtime_overrides(assembly, max_steps=max_steps, hook=hook)
    if require_assertions and not assembly.metadata.assertions:
        raise ValueError("--require-assertions was passed, but the program has no .assert directives")

    output.parent.mkdir(parents=True, exist_ok=True)
    machine_code = artifact(output, ".hack")
    driver = artifact(output, ".driver.sail")
    executable = artifact(output, ".exe") if os.name == "nt" else output
    generated = [machine_code, driver, artifact(output, ".c"), artifact(output, ".h"), executable]
    for path in generated:
        remove_artifact(path)

    write_hack(assembly, machine_code, comments)
    reloaded = load_hack(machine_code)
    if require_assertions and not reloaded.metadata.assertions:
        raise ValueError("annotated .hack reload lost required assertions")
    effective_max_steps = reloaded.metadata.max_steps or DEFAULT_MAX_STEPS
    bounded_snapshot = (
        reloaded.metadata.max_steps is not None
        and not reloaded.metadata.halt_addresses
        and bool(reloaded.metadata.assertions)
    )
    write_driver(
        reloaded,
        effective_max_steps,
        driver,
        machine_code,
        comments,
        bounded_snapshot=bounded_snapshot,
    )
    hook_source = resolve_hook_source(reloaded.metadata.hook_path)
    compile_and_run(output, driver, hook_source)


def positive_int(value: str) -> int:
    try:
        result = int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid integer: {value!r}") from error
    if result <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble and execute a Hack program with Sail")
    _ = parser.add_argument("program", type=Path)
    _ = parser.add_argument("--output", type=Path, required=True, help="generated-file prefix")
    _ = parser.add_argument("--max-steps", type=positive_int, help="override the source watchdog/bounded-run limit")
    _ = parser.add_argument("--hook", help="override the source .hook with a package-relative .sail path")
    _ = parser.add_argument("--require-assertions", action="store_true")
    _ = parser.add_argument(
        "--comments",
        choices=COMMENT_LEVELS,
        default="summary",
        help="explanatory artifact comments: none, summary (default), or full",
    )
    args = parser.parse_args()

    try:
        run(
            Path(args.program),
            Path(args.output),
            max_steps=args.max_steps,
            hook=args.hook,
            require_assertions=args.require_assertions,
            comments=args.comments,
        )
    except (AssemblyError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
