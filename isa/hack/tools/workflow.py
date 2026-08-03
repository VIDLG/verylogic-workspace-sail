from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TypedDict, cast

import tomllib

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
ROOT = PACKAGE_ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools import install_sail

MANIFEST = PACKAGE_ROOT / "programs.toml"
ISA_SOURCE = PACKAGE_ROOT / "hack.sail"
ASSEMBLER = PACKAGE_ROOT / "tools/assembler.py"
EXECUTOR = PACKAGE_ROOT / "tools/executor.py"


class Program(TypedDict):
    name: str
    source: str
    description: str


class Catalog(TypedDict):
    description: str
    programs: list[Program]


def text(entry: dict[str, object], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"{MANIFEST}: field {key!r} must be a nonempty string")
    return value


def program_name(value: str) -> str:
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"{MANIFEST}: program name must be a single path component: {value!r}")
    return value


def catalog() -> Catalog:
    with MANIFEST.open("rb") as file:
        document = cast(dict[str, object], tomllib.load(file))
    isa = document.get("isa")
    if not isinstance(isa, dict):
        raise TypeError(f"{MANIFEST} must contain an [isa] table")
    entries = document.get("programs")
    if not isinstance(entries, list):
        raise TypeError(f"{MANIFEST} must contain [[programs]] entries")

    description = text(isa, "description")
    programs: list[Program] = []
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise TypeError(f"{MANIFEST}: each [[programs]] entry must be a table")
        name = program_name(text(entry, "name"))
        if name in names:
            raise ValueError(f"{MANIFEST}: duplicate program name {name!r}")
        names.add(name)
        programs.append(
            {
                "name": name,
                "source": text(entry, "source"),
                "description": text(entry, "description"),
            }
        )
    return {"description": description, "programs": programs}


def command(args: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    _ = subprocess.run(args, cwd=cwd, env=env, check=True)


def source_path(value: str) -> Path:
    path = (PACKAGE_ROOT / value).resolve()
    try:
        path.relative_to(PACKAGE_ROOT)
    except ValueError as error:
        raise ValueError(f"{MANIFEST}: program source escapes the package: {value!r}") from error
    if not path.is_file():
        raise OSError(f"program source does not exist: {path}")
    return path


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


def assemble(entry: Program) -> None:
    output = output_prefix(entry)
    output.parent.mkdir(parents=True, exist_ok=True)
    command(
        [
            sys.executable,
            str(ASSEMBLER),
            str(source_path(entry["source"])),
            "-o",
            f"{output}.hack",
        ]
    )


def run(entry: Program, *, require_assertions: bool = False) -> None:
    output = output_prefix(entry)
    output.parent.mkdir(parents=True, exist_ok=True)
    arguments = [
        sys.executable,
        str(EXECUTOR),
        str(source_path(entry["source"])),
        "--output",
        str(output),
    ]
    if require_assertions:
        arguments.append("--require-assertions")
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
    build.mkdir()
    (build / ".gitkeep").write_text("# Sail build outputs are ignored.\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Hack ISA workflow")
    _ = parser.add_argument("action", choices=("list", "check", "asm", "run", "test", "clean"))
    _ = parser.add_argument("program", nargs="?")
    args = parser.parse_args()
    action = cast(str, args.action)
    name = cast(str | None, args.program)

    try:
        values = catalog()
        entries = values["programs"]
        sail = install_sail.ensure_installed() if action == "check" else None
        if action in {"asm", "run"}:
            if name is None:
                raise ValueError(f"{action} requires a program name")
            entry = selected_program(entries, name)
            if action == "asm":
                assemble(entry)
            else:
                run(entry)
        elif name is not None:
            raise ValueError(f"{action} does not accept a program name")
        elif action == "check":
            if sail is None:
                raise AssertionError("check requires project-local Sail")
            check(sail)
        elif action == "test":
            test(entries)
        elif action == "list":
            print(values["description"])
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
