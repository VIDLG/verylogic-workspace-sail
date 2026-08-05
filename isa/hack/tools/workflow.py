from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict, cast

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
ROOT = PACKAGE_ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from isa.hack.tools import executor
from isa.hack.tools.assembler import AssemblyError, source_description
from tools import install_sail
from tools.isa_support.cli import COMMENT_LEVELS, positive_int_arg
from tools.isa_support.process import run_checked
from tools.isa_support.publish import remove_tree

PROGRAMS = PACKAGE_ROOT / "programs"
ISA_DESCRIPTION = "nand2tetris Hack 16-bit CPU ISA"
ISA_SOURCE = PACKAGE_ROOT / "hack.sail"
ASSEMBLER = PACKAGE_ROOT / "tools/assembler_cli.py"
EXECUTOR = PACKAGE_ROOT / "tools/executor.py"
CONFORMANCE = PACKAGE_ROOT / "tests/isa_conformance.sail"


class Program(TypedDict):
    name: str
    source: Path
    description: str


def source_path(value: Path) -> Path:
    path = value.resolve()
    try:
        _ = path.relative_to(PACKAGE_ROOT)
    except ValueError as error:
        raise ValueError(f"program source escapes the package: {value}") from error
    if not path.is_file():
        raise OSError(f"program source does not exist: {path}")
    return path


def discover_programs() -> list[Program]:
    programs: list[Program] = []
    for candidate in sorted(PROGRAMS.glob("*.asm"), key=lambda path: path.name):
        source = source_path(candidate)
        try:
            description = source_description(source.read_text(encoding="utf-8"))
        except AssemblyError as error:
            raise ValueError(f"{source}: {error}") from error
        if description is None:
            raise ValueError(f"{source}: missing .description directive")
        name = source.stem
        if name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError(f"program name must be a single path component: {name!r}")
        programs.append({"name": name, "source": source, "description": description})
    return programs


def command(args: Sequence[str | os.PathLike[str]], *, cwd: Path = ROOT) -> None:
    run_checked(args, cwd=cwd)


def selected_program(entries: list[Program], name: str) -> Program:
    for entry in entries:
        if entry["name"] == name:
            return entry
    available = ", ".join(entry["name"] for entry in entries)
    raise ValueError(f"unknown program {name!r}; available: {available}")


def output_prefix(entry: Program) -> Path:
    return PACKAGE_ROOT / ".build" / entry["name"]


def check(sail: Path) -> None:
    command([str(sail), "--just-check", str(ISA_SOURCE)])


def assemble(
    entry: Program,
    *,
    max_steps: int | None = None,
    comments: str = "summary",
) -> None:
    output = output_prefix(entry)
    _ = output.parent.mkdir(parents=True, exist_ok=True)
    arguments = [
        sys.executable,
        str(ASSEMBLER),
        str(source_path(entry["source"])),
        "-o",
        f"{output}.hack",
    ]
    if max_steps is not None:
        if max_steps <= 0:
            raise ValueError("--max-steps must be a positive integer")
        arguments.extend(("--max-steps", str(max_steps)))
    arguments.extend(("--comments", comments))
    command(arguments)


def run(
    entry: Program,
    *,
    max_steps: int | None = None,
    require_assertions: bool = False,
    comments: str = "summary",
) -> None:
    output = output_prefix(entry)
    _ = output.parent.mkdir(parents=True, exist_ok=True)
    arguments = [
        sys.executable,
        str(EXECUTOR),
        str(source_path(entry["source"])),
        "--output",
        str(output),
    ]
    if max_steps is not None:
        if max_steps <= 0:
            raise ValueError("--max-steps must be a positive integer")
        arguments.extend(("--max-steps", str(max_steps)))
    if require_assertions:
        arguments.append("--require-assertions")
    arguments.extend(("--comments", comments))
    command(arguments)


def test(entries: list[Program]) -> None:
    command([sys.executable, "-m", "pytest", "isa/hack/tests"], cwd=ROOT)
    build = PACKAGE_ROOT / ".build"
    build.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".conformance.", dir=build) as temporary:
        executor.compile_and_run(Path(temporary) / "isa_conformance", CONFORMANCE)
    for entry in entries:
        print(f"testing {entry['name']}")
        run(entry, require_assertions=True)


def clean() -> None:
    build = PACKAGE_ROOT / ".build"
    remove_tree(build)
    _ = build.mkdir()
    _ = (build / ".gitkeep").write_text(
        "# Sail build outputs are ignored.\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Hack ISA workflow")
    _ = parser.add_argument(
        "action", choices=("list", "check", "assemble", "run", "test", "clean")
    )
    _ = parser.add_argument("program", nargs="?")
    _ = parser.add_argument(
        "--comments",
        choices=COMMENT_LEVELS,
        default="summary",
        help="explanatory artifact comments for assemble/run (default: summary)",
    )
    _ = parser.add_argument(
        "--max-steps",
        type=positive_int_arg,
        help="assemble/run override for source .max_steps",
    )

    args = parser.parse_args()
    action = cast(str, args.action)
    name = cast(str | None, args.program)
    comments = cast(str, args.comments)
    max_steps = cast(int | None, args.max_steps)

    try:
        entries = discover_programs()
        sail = install_sail.ensure_installed() if action == "check" else None
        if action in {"assemble", "run"}:
            if name is None:
                raise ValueError(f"{action} requires a program name")
            entry = selected_program(entries, name)
            if action == "assemble":
                assemble(entry, max_steps=max_steps, comments=comments)
            else:
                run(entry, max_steps=max_steps, comments=comments)
        elif name is not None:
            raise ValueError(f"{action} does not accept a program name")
        elif comments != "summary":
            raise ValueError(f"{action} does not accept --comments")
        elif max_steps is not None:
            raise ValueError(f"{action} does not accept --max-steps")
        elif action == "check":
            if sail is None:
                raise AssertionError("check requires project-local Sail")
            check(sail)
        elif action == "test":
            test(entries)
        elif action == "list":
            print(ISA_DESCRIPTION)
            for entry in entries:
                print(f"  {entry['name']}: {entry['description']}")
        else:
            clean()
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
