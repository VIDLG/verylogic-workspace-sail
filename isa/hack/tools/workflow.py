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
from isa.hack.tools.profiles import (
    DEFAULT_PROFILE,
    PROFILES,
    Profile,
    get_profile,
    validate_registry,
)
from tools import install_sail
from tools.isa_support.cli import COMMENT_LEVELS, positive_int_arg
from tools.isa_support.process import run_checked
from tools.isa_support.publish import remove_tree

PROGRAMS = PACKAGE_ROOT / "programs"
ISA_DESCRIPTION = "Hack ISA profiles: hack16 and hack32"
ASSEMBLER = PACKAGE_ROOT / "tools/assembler_cli.py"
EXECUTOR = PACKAGE_ROOT / "tools/executor.py"


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


def output_prefix(entry: Program, profile: Profile) -> Path:
    name = entry["name"]
    return PACKAGE_ROOT / ".build" / profile.name / "asm" / name / name


def conformance_project(profile: Profile) -> Path:
    return PACKAGE_ROOT / f"tests/sail/{profile.name}/conformance.sail_project"


def check(sail: Path, profile: Profile | None = None) -> None:
    selected = (profile,) if profile is not None else tuple(PROFILES.values())
    for item in selected:
        command(
            [
                str(sail),
                "--project",
                str(item.sail_project),
                "--all-modules",
                "--list-files",
            ]
        )
        command(
            [
                str(sail),
                "--project",
                str(item.sail_project),
                "--project",
                str(conformance_project(item)),
                "--all-modules",
                "--just-check",
            ]
        )


def assemble(
    entry: Program,
    *,
    max_steps: int | None = None,
    comments: str = "summary",
    profile: Profile | None = None,
) -> None:
    selected_profile = profile or get_profile(DEFAULT_PROFILE)
    output = output_prefix(entry, selected_profile)
    _ = output.parent.mkdir(parents=True, exist_ok=True)
    arguments = [
        sys.executable,
        str(ASSEMBLER),
        str(source_path(entry["source"])),
        "-o",
        f"{output}.hack",
        "--profile",
        selected_profile.name,
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
    profile: Profile | None = None,
) -> None:
    selected_profile = profile or get_profile(DEFAULT_PROFILE)
    output = output_prefix(entry, selected_profile)
    _ = output.parent.mkdir(parents=True, exist_ok=True)
    arguments = [
        sys.executable,
        str(EXECUTOR),
        str(source_path(entry["source"])),
        "--output",
        str(output),
        "--profile",
        selected_profile.name,
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
    validate_registry()
    command([sys.executable, "-m", "pytest", "isa/hack/tests"], cwd=ROOT)
    build = PACKAGE_ROOT / ".build"
    build.mkdir(parents=True, exist_ok=True)
    for profile in PROFILES.values():
        profile_build = build / profile.name
        profile_build.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".conformance.", dir=profile_build
        ) as temporary:
            executor.compile_and_run(
                profile,
                Path(temporary) / "isa_conformance",
                conformance_project(profile),
            )
        for entry in entries:
            print(f"testing {profile.name}/{entry['name']}")
            run(entry, require_assertions=True, profile=profile)


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
        "--profile",
        choices=tuple(PROFILES),
        help="narrow check or select assemble/run profile; default run profile is hack16",
    )
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
    profile_name = cast(str | None, args.profile)

    try:
        entries = discover_programs()
        sail = install_sail.ensure_installed() if action == "check" else None
        if action in {"assemble", "run"}:
            if name is None:
                raise ValueError(f"{action} requires a program name")
            entry = selected_program(entries, name)
            profile = get_profile(profile_name or DEFAULT_PROFILE)
            if action == "assemble":
                assemble(
                    entry,
                    max_steps=max_steps,
                    comments=comments,
                    profile=profile,
                )
            else:
                run(
                    entry,
                    max_steps=max_steps,
                    comments=comments,
                    profile=profile,
                )
        elif name is not None:
            raise ValueError(f"{action} does not accept a program name")
        elif comments != "summary":
            raise ValueError(f"{action} does not accept --comments")
        elif max_steps is not None:
            raise ValueError(f"{action} does not accept --max-steps")
        elif action == "check":
            if sail is None:
                raise AssertionError("check requires project-local Sail")
            check(sail, None if profile_name is None else get_profile(profile_name))
        elif profile_name is not None:
            raise ValueError(f"{action} does not accept --profile")
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
