import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from tools import install_sail


def test_select_release_for_each_supported_target() -> None:
    assert install_sail.select_release("win32", "AMD64").asset == "sail-Windows-AMD64.zip"
    assert install_sail.select_release("linux", "x86_64").asset == "sail-Linux-x86_64.tar.gz"
    assert install_sail.select_release("linux", "aarch64").asset == "sail-Linux-aarch64.tar.gz"


def test_select_release_reports_macos_asset_limitation() -> None:
    with pytest.raises(RuntimeError, match="no official macOS binary asset"):
        install_sail.select_release("darwin", "arm64")


def test_installed_requires_the_selected_asset_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    release = install_sail.select_release("win32", "amd64")
    other_release = install_sail.select_release("linux", "x86_64")
    install_dir = tmp_path / "sail"
    marker = install_dir / ".installed.json"
    monkeypatch.setattr(install_sail, "INSTALL_DIR", install_dir)
    monkeypatch.setattr(install_sail, "MARKER", marker)

    executable = install_sail.local_executable(release)
    executable.parent.mkdir(parents=True)
    executable.touch()
    marker.write_text(install_sail.marker_contents(release), encoding="ascii")
    assert install_sail.installed(release)

    marker.write_text(install_sail.marker_contents(other_release), encoding="ascii")
    assert not install_sail.installed(release)


def test_extract_zip_rejects_symbolic_links(tmp_path: Path) -> None:
    archive = tmp_path / "sail.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        member = zipfile.ZipInfo("sail/bin/sail.exe")
        member.external_attr = 0o120777 << 16
        bundle.writestr(member, "target")

    release = install_sail.select_release("win32", "amd64")
    with pytest.raises(ValueError, match="non-regular"):
        install_sail.extract(archive, tmp_path / "extracted", release)


def test_extract_tar_rejects_hard_links(tmp_path: Path) -> None:
    archive = tmp_path / "sail.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        member = tarfile.TarInfo("sail/bin/sail")
        member.type = tarfile.LNKTYPE
        member.linkname = "elsewhere"
        bundle.addfile(member, io.BytesIO())

    release = install_sail.select_release("linux", "x86_64")
    with pytest.raises(ValueError, match="non-regular"):
        install_sail.extract(archive, tmp_path / "extracted", release)
