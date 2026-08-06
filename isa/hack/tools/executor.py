from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
ROOT = PACKAGE_ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from isa.hack.tools.artifact import (
    LoadedHack,
    apply_runtime_overrides,
    load_hack,
    write_hack,
)
from isa.hack.tools.assembler import (
    AssemblyError,
    Assertion,
    assemble,
)
from isa.hack.tools.profiles import DEFAULT_PROFILE, Profile, get_profile
from tools import install_sail
from tools.isa_support.cli import (
    COMMENT_LEVELS,
    positive_int_arg,
    validate_comment_level,
)
from tools.isa_support.host_c import compile_sail_generated_c
from tools.isa_support.manifest import render_preamble
from tools.isa_support.process import run_checked
from tools.isa_support.publish import publish_artifact_closure


def command(args: Sequence[str | os.PathLike[str]]) -> None:
    run_checked(args, cwd=ROOT)


def artifact_path(prefix: Path, suffix: str) -> Path:
    return Path(f"{prefix}{suffix}")


def _assertion_location(target: str) -> str:
    if target.startswith("R") and target[1:].isdigit():
        return f"RAM[{int(target[1:])}]"
    return target


def _assertion_expression(assertion: Assertion, profile: Profile) -> str:
    location = _assertion_location(assertion.target)
    if assertion.operator in {"==", "!="}:
        literal = (
            f"0b{assertion.value:015b}"
            if assertion.target == "PC"
            else f"0x{assertion.value:0{profile.hex_digits}X}"
        )
        return f"{location} {assertion.operator} {literal}"
    return f"{assertion.mode}({location}) {assertion.operator} {assertion.value}"


def _assertion_source(assertion: Assertion, profile: Profile) -> str:
    target = assertion.display_target or assertion.target
    if assertion.operator in {"==", "!="}:
        value = (
            f"0b{assertion.value:015b}"
            if assertion.target == "PC"
            else f"0x{assertion.value:0{profile.hex_digits}X}"
        )
    else:
        value = str(assertion.value)
    return f"{target} {assertion.operator} {value}"


def write_driver(
    program: LoadedHack,
    path: Path,
    binary: Path,
    comments: str = "summary",
    bounded_snapshot: bool = False,
) -> None:
    comments = validate_comment_level(comments)
    manifest = program.manifest
    if manifest.comments != comments:
        raise ValueError(
            f"artifact comment level {manifest.comments!r} "
            f"does not match driver level {comments!r}"
        )
    profile = program.profile
    words = program.words
    metadata = program.metadata
    max_steps = metadata.max_steps
    if bounded_snapshot and (
        metadata.max_steps_origin == "default"
        or metadata.halt_addresses
        or not metadata.assertions
    ):
        raise ValueError(
            "bounded snapshot requires max_steps, assertions, and no lowered HALT"
        )

    load_lines: list[str] = []
    for address, word in enumerate(words):
        suffix = ""
        if comments != "none":
            source = (
                program.word_comments[address]
                if address < len(program.word_comments)
                else None
            )
            annotation = source or f"ROM[{address:04d}]"
            suffix = f" // {annotation}"
        load_lines.append(f"  ROM[{address}] = 0b{word:0{profile.word_bits}b};{suffix}")
    loads = "\n".join(load_lines)
    halt_lines: list[str] = []
    for index, address in enumerate(metadata.halt_addresses):
        suffix = (
            ""
            if comments == "none"
            else (
                f" // Lowered HALT metadata at ROM[{address:04d}]; not an ISA encoding."
            )
        )
        halt_lines.append(
            f"let lowered_halt_{index} : program_counter = 0b{address:015b}{suffix}"
        )
    halt_values = "" if not halt_lines else "\n".join(halt_lines) + "\n"
    not_halted_condition = " & ".join(
        f"(pc != lowered_halt_{index})" for index in range(len(metadata.halt_addresses))
    )
    halted_condition = (
        " | ".join(
            f"PC == lowered_halt_{index}"
            for index in range(len(metadata.halt_addresses))
        )
        or "false"
    )
    pending_condition = "unsigned(pc) < loaded_rom_words"
    if not_halted_condition:
        pending_condition = f"{not_halted_condition} & {pending_condition}"

    assertion_lines: list[str] = []
    for assertion in metadata.assertions:
        if comments == "full":
            assertion_lines.append(
                f"  // Source line {assertion.line}: .assert "
                f"{_assertion_source(assertion, profile)}"
            )
        assertion_lines.append(
            f'  assert ({_assertion_expression(assertion, profile)}, "assertion '
            f"{_assertion_source(assertion, profile)} from source line "
            f'{assertion.line} failed");'
        )
    assertions = "\n".join(assertion_lines)
    status = "ASSERT PASS" if metadata.assertions else "RUN COMPLETE"

    inline_step_doc = (
        ""
        if comments == "none"
        else ("    // Run one model-owned fetch, decode, and execute step.\n")
    )
    step_body = f"""{inline_step_doc}    hack_step();
    steps = steps + 1"""
    continue_condition = f"{pending_condition} & steps < driver_max_steps"
    if bounded_snapshot:
        limit_check = ""
    elif metadata.halt_addresses:
        limit_check = f'  assert ({halted_condition}, "maximum step limit reached before lowered HALT");\n'
    else:
        limit_check = '  assert (false, "maximum step limit reached without lowered HALT or an explicit bounded snapshot");\n'
    loop = f"""  while execution_should_continue(PC, steps) {{
{step_body}
  }};"""

    human_preamble = render_preamble(manifest, comments)
    header = (
        ""
        if comments == "none"
        else (
            f"// Generated by executor.py from {binary.name}; regenerate instead of editing.\n"
        )
    )
    size_doc = (
        ""
        if comments == "none"
        else ("// Loaded artifact size, not an execution step limit.\n")
    )
    step_limit = f"let driver_max_steps : int = {max_steps}\n"
    load_doc = (
        ""
        if comments == "none"
        else ("// Load raw machine words into the model-owned ROM before execution.\n")
    )
    continue_doc = (
        ""
        if comments == "none"
        else (
            "// Return whether another instruction attempt may begin; this does not declare successful completion.\n"
        )
    )
    main_doc = (
        ""
        if comments == "none"
        else (
            "// Load the ROM, run while another attempt is allowed, then validate why execution stopped.\n"
        )
    )

    after_loop_doc = (
        ""
        if comments != "full"
        else (
            "  // Distinguish valid HALT/bounded completion from leaving the loaded image or watchdog failure.\n"
        )
    )
    output_doc = (
        ""
        if comments != "full"
        else (
            "  // This dump is diagnostic; Sail assertions and exit status determine success.\n"
        )
    )

    path.write_text(
        f"""{human_preamble}{header}{size_doc}let loaded_rom_words : int = {len(words)}
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
{loop}
{after_loop_doc}  assert (unsigned(PC) < loaded_rom_words, "program counter left the loaded ROM image");
{limit_check}{assertions}
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
        newline="\n",
    )


def write_driver_project(profile: Profile, driver: Path, project: Path) -> None:
    if driver.parent.resolve() != project.parent.resolve():
        raise ValueError("driver and companion project must share a directory")
    project.write_text(
        f"""hack_driver {{
  requires {profile.name}_profile
  files \"{driver.name}\"
}}
""",
        encoding="utf-8",
        newline="\n",
    )


def compile_and_run(profile: Profile, output: Path, driver_project: Path) -> None:
    sail = install_sail.ensure_installed()
    command(
        [
            sail,
            "--project",
            profile.sail_project,
            "--project",
            driver_project,
            "--all-modules",
            "-c",
            "-o",
            output,
        ]
    )
    executable = artifact_path(output, ".exe") if os.name == "nt" else output
    compile_sail_generated_c(sail, artifact_path(output, ".c"), executable, ROOT)
    command([executable])


def run(
    program: Path,
    output: Path,
    max_steps: int | None = None,
    require_assertions: bool = False,
    comments: str = "summary",
    profile: str = DEFAULT_PROFILE,
) -> None:
    comments = validate_comment_level(comments)
    selected_profile = get_profile(profile)
    if max_steps is not None and max_steps <= 0:
        raise ValueError("--max-steps must be a positive integer")
    if output.name in {"", ".", ".."}:
        raise ValueError("--output must be a file prefix")

    assembly = assemble(program, profile=selected_profile.name)
    if len(assembly.records) > selected_profile.rom_words:
        raise ValueError(
            f"program exceeds the {selected_profile.rom_words}-word Hack ROM"
        )
    assembly = apply_runtime_overrides(assembly, max_steps=max_steps)
    if require_assertions and not assembly.metadata.assertions:
        raise ValueError(
            "--require-assertions was passed, but the program has no .assert directives"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output.name}.run.",
        dir=output.parent,
    ) as temporary:
        staged_output = Path(temporary) / output.name
        staged_machine = artifact_path(staged_output, ".hack")
        staged_driver = artifact_path(staged_output, ".driver.sail")
        staged_driver_project = artifact_path(staged_output, ".driver.sail_project")
        staged_executable = (
            artifact_path(staged_output, ".exe") if os.name == "nt" else staged_output
        )

        write_hack(assembly, staged_machine, comments)
        reloaded = load_hack(staged_machine, expected_profile=selected_profile.name)

        if require_assertions and not reloaded.metadata.assertions:
            raise ValueError("annotated .hack reload lost required assertions")
        bounded_snapshot = (
            reloaded.metadata.max_steps_origin != "default"
            and not reloaded.metadata.halt_addresses
            and bool(reloaded.metadata.assertions)
        )
        write_driver(
            reloaded,
            staged_driver,
            staged_machine,
            comments,
            bounded_snapshot=bounded_snapshot,
        )
        write_driver_project(reloaded.profile, staged_driver, staged_driver_project)
        compile_and_run(reloaded.profile, staged_output, staged_driver_project)

        staged = (
            staged_machine,
            staged_driver,
            staged_driver_project,
            artifact_path(staged_output, ".c"),
            artifact_path(staged_output, ".h"),
            staged_executable,
        )
        final_executable = artifact_path(output, ".exe") if os.name == "nt" else output
        final = (
            artifact_path(output, ".hack"),
            artifact_path(output, ".driver.sail"),
            artifact_path(output, ".driver.sail_project"),
            artifact_path(output, ".c"),
            artifact_path(output, ".h"),
            final_executable,
        )
        publish_artifact_closure(zip(staged, final, strict=True))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Assemble and execute a Hack program with Sail"
    )
    _ = parser.add_argument("program", type=Path)
    _ = parser.add_argument(
        "--output", type=Path, required=True, help="generated-file prefix"
    )
    _ = parser.add_argument(
        "--max-steps",
        type=positive_int_arg,
        help="override the source watchdog/bounded-run limit",
    )

    _ = parser.add_argument("--require-assertions", action="store_true")
    _ = parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help="Hack architecture profile: hack16 (default) or hack32",
    )
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
            require_assertions=args.require_assertions,
            comments=args.comments,
            profile=args.profile,
        )
    except (AssemblyError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
