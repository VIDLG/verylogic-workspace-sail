from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from .process import run_checked

SAIL_RUNTIME_SOURCES = ("rts", "elf", "sail", "sail_config", "sail_failure", "cJSON")
_THROW_LOCATION_ASSIGNMENT = re.compile(
    r'(?P<prefix>COPY\(sail_string\)\(throw_location, ")'
    r'(?P<location>[^"\r\n]*)'
    r'(?P<suffix>"\);)'
)


def normalize_sail_c_throw_locations(generated_c: Path) -> None:
    source = generated_c.read_text(encoding="utf-8")
    normalized = _THROW_LOCATION_ASSIGNMENT.sub(
        lambda match: (
            match.group("prefix")
            + match.group("location").replace("\\", "/")
            + match.group("suffix")
        ),
        source,
    )
    if normalized != source:
        generated_c.write_text(normalized, encoding="utf-8", newline="\n")


def host_c_compiler() -> str:
    if os.name == "nt":
        return "x86_64-w64-mingw32-gcc"
    if sys.platform.startswith("linux"):
        return "gcc"
    raise OSError(f"unsupported host C compiler platform: {sys.platform}")


def compile_sail_generated_c(
    sail_executable: Path,
    generated_c: Path,
    executable: Path,
    workspace_root: Path,
) -> None:
    sail_lib = sail_executable.parent.parent / "share/sail/lib"
    if not sail_lib.is_dir():
        raise OSError(f"Sail C runtime not found: {sail_lib}")

    # Sail 0.20.2 emits Windows exception locations as unescaped C strings.
    # Forward slashes preserve the diagnostic path while keeping generated C valid.
    normalize_sail_c_throw_locations(generated_c)

    compat_header = workspace_root / "support/sail_windows_compat.h"
    compat_source = workspace_root / "support/sail_windows_compat.c"
    args = [
        host_c_compiler(),
        "-include",
        str(compat_header),
        f"-I{sail_lib}",
        "-o",
        str(executable),
        str(generated_c),
        *[str(sail_lib / f"{name}.c") for name in SAIL_RUNTIME_SOURCES],
        str(compat_source),
        "-lgmp",
    ]

    conda_prefix = os.environ.get("CONDA_PREFIX")
    if os.name == "nt":
        if conda_prefix is None:
            raise OSError("CONDA_PREFIX is required to locate GMP on Windows")
        conda = Path(conda_prefix)
        args[4:4] = [f"-I{conda / 'Library/include'}", f"-L{conda / 'Library/lib'}"]
    elif conda_prefix:
        conda = Path(conda_prefix)
        args[4:4] = [f"-I{conda / 'include'}", f"-L{conda / 'lib'}"]

    run_checked(args, cwd=workspace_root)
