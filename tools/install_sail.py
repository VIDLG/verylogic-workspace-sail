from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parent.parent
INSTALL_DIR = ROOT / ".pixi/sail"
MARKER = INSTALL_DIR / ".installed.json"
VERSION = "0.20.2-binary"
RELEASE_BASE_URL = f"https://github.com/rems-project/sail/releases/download/{VERSION}"


@dataclass(frozen=True)
class Release:
    system: str
    machines: frozenset[str]
    asset: str
    sha256: str
    executable: str

    @property
    def url(self) -> str:
        return f"{RELEASE_BASE_URL}/{self.asset}"


RELEASES = (
    Release(
        "win32",
        frozenset({"amd64", "x86_64"}),
        "sail-Windows-AMD64.zip",
        "98e6f4f791fc53019d843a46aa9f377ca9374155d8e448b0eca2190b017b2e75",
        "bin/sail.exe",
    ),
    Release(
        "linux",
        frozenset({"x86_64", "amd64"}),
        "sail-Linux-x86_64.tar.gz",
        "26b59bcab2d66e9f220d317dfe45f8b09170ed70e59a824553d6f525134d1ff6",
        "bin/sail",
    ),
    Release(
        "linux",
        frozenset({"aarch64", "arm64"}),
        "sail-Linux-aarch64.tar.gz",
        "10428d1be9a2945a71f9855c81027c22d6a2895dbbcf2ce9a4f9640203d5067f",
        "bin/sail",
    ),
)


def select_release(system: str, machine: str) -> Release:
    normalized_machine = machine.lower() or "unknown"
    for release in RELEASES:
        if release.system == system and normalized_machine in release.machines:
            return release
    detected = f"{system}/{machine or 'unknown'}"
    if system == "darwin":
        raise RuntimeError(
            "macOS is unsupported: Sail 0.20.2-binary has no official macOS binary asset "
            f"(detected {detected})"
        )
    raise RuntimeError(
        "Sail 0.20.2-binary supports Windows AMD64, Linux x86_64, and Linux aarch64 "
        f"(detected {detected})"
    )


def selected_release() -> Release:
    return select_release(sys.platform, platform.machine())


def local_executable(release: Release | None = None) -> Path:
    return INSTALL_DIR / (release or selected_release()).executable


def marker_contents(release: Release) -> str:
    return json.dumps(
        {"asset": release.asset, "sha256": release.sha256, "version": VERSION},
        sort_keys=True,
    ) + "\n"


def installed(release: Release | None = None) -> bool:
    release = release or selected_release()
    executable = local_executable(release)
    try:
        marker = MARKER.read_text(encoding="ascii")
    except OSError:
        return False
    return executable.is_file() and not executable.is_symlink() and marker == marker_contents(release)


def ensure_installed() -> Path:
    release = selected_release()
    if not installed(release):
        install(False)
    executable = local_executable(release)
    if not executable.is_file():
        raise OSError(f"project-local Sail executable was not installed: {executable}")
    return executable.resolve()


def download(destination: Path, release: Release) -> None:
    digest = hashlib.sha256()
    request = urllib.request.Request(release.url, headers={"User-Agent": "verylogic-workspace-sail installer"})
    with urllib.request.urlopen(request) as response, destination.open("wb") as file:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            file.write(chunk)
    if digest.hexdigest() != release.sha256:
        destination.unlink(missing_ok=True)
        raise ValueError("downloaded Sail archive does not match its pinned SHA-256")


def archive_path(destination: Path, name: str) -> Path:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or PureWindowsPath(name).is_absolute()
        or ":" in path.parts[0]
    ):
        raise ValueError(f"unsafe path in Sail archive: {name}")
    return destination.joinpath(*path.parts)


def extract_zip(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = archive_path(destination, member.filename)
            mode = member.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if stat.S_ISLNK(mode) or (file_type not in {0, stat.S_IFREG, stat.S_IFDIR}):
                raise ValueError(f"unsafe non-regular entry in Sail archive: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)


def extract_tar(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            target = archive_path(destination, member.name)
            if not (member.isdir() or member.isfile()):
                raise ValueError(f"unsafe non-regular entry in Sail archive: {member.name}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                source = bundle.extractfile(member)
                if source is None:
                    raise ValueError(f"cannot read Sail archive entry: {member.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(stat.S_IMODE(member.mode))


def extract(archive: Path, destination: Path, release: Release) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    if release.asset.endswith(".zip"):
        extract_zip(archive, destination)
    elif release.asset.endswith(".tar.gz"):
        extract_tar(archive, destination)
    else:
        raise ValueError(f"unsupported Sail archive format: {release.asset}")

    executable_parts = PurePosixPath(release.executable).parts
    candidates = [
        path
        for path in destination.rglob(executable_parts[-1])
        if path.is_file() and path.relative_to(destination).parts[-len(executable_parts):] == executable_parts
    ]
    if len(candidates) != 1:
        raise ValueError(f"Sail archive must contain exactly one {release.executable}")
    executable = candidates[0]
    if release.system != "win32":
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable.parents[len(executable_parts) - 1]


def install(force: bool) -> None:
    release = selected_release()
    if installed(release) and not force:
        print(f"Sail {VERSION} ({release.asset}) is already installed in {INSTALL_DIR}")
        return

    state_dir = INSTALL_DIR.parent
    state_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sail-", dir=state_dir) as temporary:
        temporary_dir = Path(temporary)
        archive = temporary_dir / release.asset
        extracted = temporary_dir / "extracted"
        print(f"Downloading Sail {VERSION} ({release.asset})...")
        download(archive, release)
        package = extract(archive, extracted, release)
        (package / MARKER.name).write_text(marker_contents(release), encoding="ascii")
        previous = temporary_dir / "previous"
        if INSTALL_DIR.exists():
            INSTALL_DIR.replace(previous)
        try:
            package.replace(INSTALL_DIR)
        except OSError:
            if previous.exists() and not INSTALL_DIR.exists():
                previous.replace(INSTALL_DIR)
            raise
    print(f"Installed Sail {VERSION} ({release.asset}) in {INSTALL_DIR}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the pinned Sail binary into .pixi/sail")
    _ = parser.add_argument("--force", action="store_true", help="replace the existing project-local installation")
    args = parser.parse_args()
    try:
        install(args.force)
    except (OSError, RuntimeError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
