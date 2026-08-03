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
    comments: str = "full",
) -> None:
    comments = validate_comment_level(comments)
    words = program.words
    metadata = program.metadata

    case_lines: list[str] = []
    for address, word in enumerate(words):
        suffix = ""
        if comments != "none":
            source = program.word_comments[address] if address < len(program.word_comments) else None
            annotation = source or f"ROM[{address:04d}]"
            suffix = f" // {annotation}"
        case_lines.append(f"    0b{address:015b} => encdec(0b{word:016b}),{suffix}")
    cases = "\n".join(case_lines)
    completion_cases = "\n".join(
        f"    0b{address:015b} => true," for address in metadata.halt_addresses
    )

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

    if max_steps is None:
        loop = """  while execution_complete(PC) == false {
    hack_hook_before_step(steps);
    execute(instruction_at(PC));
    steps = steps + 1;
    hack_hook_after_step(steps)
  };"""
        limit_check = ""
    else:
        loop = f"""  while (if execution_complete(PC) then false else steps < {max_steps}) {{
    hack_hook_before_step(steps);
    execute(instruction_at(PC));
    steps = steps + 1;
    hack_hook_after_step(steps)
  }};"""
        deliberately_bounded = not metadata.halt_addresses and bool(metadata.assertions)
        limit_check = "" if deliberately_bounded else (
            '  assert (execution_complete(PC), "maximum step limit reached before HALT or ROM end");\n'
        )

    header = "" if comments == "none" else (
        f"// Generated by executor.py from {binary.name}; regenerate instead of editing.\n"
    )
    instruction_doc = "" if comments == "none" else (
        "// Decode the ROM word selected by the 15-bit program counter.\n"
    )
    completion_doc = "" if comments == "none" else (
        "// Stop at a lowered HALT self-loop or after the final ROM word.\n"
    )
    main_doc = "" if comments == "none" else (
        "// Execute instructions, evaluate source assertions, then print architectural state.\n"
    )
    before_run_doc = "" if comments != "full" else (
        "  // Hooks share this process and observe the same A, D, PC, and RAM state.\n"
    )
    after_loop_doc = "" if comments != "full" else (
        "  // The loop has reached HALT, ROM end, or the configured bounded snapshot.\n"
    )
    output_doc = "" if comments != "full" else (
        "  // This dump is diagnostic; Sail assertions and exit status determine success.\n"
    )

    path.write_text(
        f"""{header}{instruction_doc}function instruction_at(pc : program_counter) -> instruction = {{
  match pc {{
{cases}
    _ => AInstruction(0b000000000000000)
  }}
}}

{completion_doc}function execution_complete(pc : program_counter) -> bool = {{
  match pc {{
{completion_cases}
    _ => unsigned(pc) >= {len(words)}
  }}
}}

{main_doc}function main() -> unit = {{
  var steps : int = 0;
{before_run_doc}  hack_hook_before_run();
{loop}
{after_loop_doc}{limit_check}{assertions}
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
    require_assertions: bool = False,
    comments: str = "full",
) -> None:
    comments = validate_comment_level(comments)
    if max_steps is not None and max_steps <= 0:
        raise ValueError("--max-steps must be a positive integer")
    if output.name in {"", ".", ".."}:
        raise ValueError("--output must be a file prefix")

    assembly = assemble(program)
    if len(assembly.records) > 32768:
        raise ValueError("program exceeds the 32768-word Hack ROM")
    effective_max_steps = max_steps if max_steps is not None else assembly.metadata.max_steps
    if require_assertions and not assembly.metadata.assertions:
        raise ValueError("--require-assertions was passed, but the program has no .assert directives")
    if len(assembly.records) == 32768 and not assembly.metadata.halt_addresses and effective_max_steps is None:
        raise ValueError("a full 32768-word ROM needs HALT or max_steps because PC cannot represent ROM end")

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
    write_driver(reloaded, effective_max_steps, driver, machine_code, comments)
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
    _ = parser.add_argument("--require-assertions", action="store_true")
    _ = parser.add_argument(
        "--comments",
        choices=COMMENT_LEVELS,
        default="full",
        help="explanatory artifact comments: none, summary, or full (default)",
    )
    args = parser.parse_args()

    try:
        run(
            Path(args.program),
            Path(args.output),
            max_steps=args.max_steps,
            require_assertions=args.require_assertions,
            comments=args.comments,
        )
    except (AssemblyError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
