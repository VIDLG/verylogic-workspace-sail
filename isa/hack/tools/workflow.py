from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TypedDict, cast

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
ROOT = PACKAGE_ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from isa.hack.tools.assembler import COMMENT_LEVELS, AssemblyError, source_description
from tools import install_sail

PROGRAMS = PACKAGE_ROOT / "programs"
ISA_DESCRIPTION = "nand2tetris Hack 16-bit CPU ISA"
ISA_SOURCE = PACKAGE_ROOT / "hack.sail"
ASSEMBLER = PACKAGE_ROOT / "tools/assembler.py"
EXECUTOR = PACKAGE_ROOT / "tools/executor.py"


class Program(TypedDict):
    name: str
    source: Path
    description: str


def source_path(value: Path) -> Path:
    path = value.resolve()
    try:
        path.relative_to(PACKAGE_ROOT)
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
        programs.append(Program(name=name, source=source, description=description))
    return programs


def command(args: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    _ = subprocess.run(args, cwd=cwd, env=env, check=True)


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


def assemble(entry: Program, *, comments: str = "full") -> None:
    output = output_prefix(entry)
    _ = output.parent.mkdir(parents=True, exist_ok=True)
    command(
        [
            sys.executable,
            str(ASSEMBLER),
            str(source_path(entry["source"])),
            "-o",
            f"{output}.hack",
            "--comments",
            comments,
        ]
    )


def run(
    entry: Program,
    *,
    require_assertions: bool = False,
    comments: str = "full",
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
    if require_assertions:
        arguments.append("--require-assertions")
    arguments.extend(("--comments", comments))
    command(arguments)


def test(entries: list[Program]) -> None:
    environment = os.environ.copy()
    root = str(ROOT)
    environment["PYTHONPATH"] = root if not environment.get("PYTHONPATH") else f"{root}{os.pathsep}{environment['PYTHONPATH']}"
    command([sys.executable, "-m", "pytest", "tests"], cwd=PACKAGE_ROOT, env=environment)
    for entry in entries:
        print(f"testing {entry['name']}")
        run(entry, require_assertions=True)


def clean() -> None:
    build = PACKAGE_ROOT / ".build"
    if build.exists():
        try:
            shutil.rmtree(build)
        except PermissionError:
            username = os.environ.get("USERNAME")
            if sys.platform != "win32" or not username:
                raise
            command(["icacls", str(build), "/grant", f"{username}:(F)", "/T"])
            shutil.rmtree(build)
    _ = build.mkdir()
    _ = (build / ".gitkeep").write_text("# Sail build outputs are ignored.\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Hack ISA workflow")
    _ = parser.add_argument("action", choices=("list", "check", "asm", "run", "test", "clean"))
    _ = parser.add_argument("program", nargs="?")
    _ = parser.add_argument(
        "--comments",
        choices=COMMENT_LEVELS,
        default="full",
        help="explanatory artifact comments for asm/run (default: full)",
    )
    args = parser.parse_args()
    action = cast(str, args.action)
    name = cast(str | None, args.program)
    comments = cast(str, args.comments)

    try:
        entries = discover_programs()
        sail = install_sail.ensure_installed() if action == "check" else None
        if action in {"asm", "run"}:
            if name is None:
                raise ValueError(f"{action} requires a program name")
            entry = selected_program(entries, name)
            if action == "asm":
                assemble(entry, comments=comments)
            else:
                run(entry, comments=comments)
        elif name is not None:
            raise ValueError(f"{action} does not accept a program name")
        elif comments != "full":
            raise ValueError(f"{action} does not accept --comments")
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
    except (OSError, RuntimeError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
