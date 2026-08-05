from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import warnings
from collections.abc import Iterable
from pathlib import Path


def _grant_windows_access(path: Path, *, recursive: bool = False) -> None:
    username = os.environ.get("USERNAME")
    if os.name != "nt" or not username:
        raise PermissionError(f"cannot update permissions for {path}")
    arguments = ["icacls", str(path), "/grant", f"{username}:(F)"]
    if recursive:
        arguments.append("/T")
    subprocess.run(arguments, check=True, capture_output=True, text=True)


def remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        _grant_windows_access(path)
        path.unlink(missing_ok=True)


def remove_tree(path: Path) -> None:
    if not path.exists():
        return
    try:
        shutil.rmtree(path)
    except PermissionError:
        _grant_windows_access(path, recursive=True)
        shutil.rmtree(path)


def replace_path(source: Path, destination: Path) -> None:
    try:
        os.replace(source, destination)
    except PermissionError:
        _grant_windows_access(source)
        if destination.exists():
            _grant_windows_access(destination)
        os.replace(source, destination)


def publish_artifact_closure(replacements: Iterable[tuple[Path, Path]]) -> None:
    staged = list(replacements)
    if not staged:
        return

    destinations = [destination for _, destination in staged]
    if len(set(destinations)) != len(destinations):
        raise ValueError("artifact destinations must be unique")
    for source, _ in staged:
        if not source.is_file():
            raise OSError(f"staged artifact does not exist: {source}")
    for _, destination in staged:
        destination.parent.mkdir(parents=True, exist_ok=True)

    backups: list[tuple[Path, Path]] = []
    installed: list[Path] = []
    try:
        for destination in destinations:
            if destination.exists():
                handle, backup_name = tempfile.mkstemp(
                    prefix=f".{destination.name}.backup.", dir=destination.parent
                )
                os.close(handle)
                backup = Path(backup_name)
                remove_file(backup)
                replace_path(destination, backup)
                backups.append((backup, destination))
        for source, destination in staged:
            replace_path(source, destination)
            installed.append(destination)
    except (Exception, KeyboardInterrupt) as publication_error:
        rollback_errors: list[str] = []
        backed_up_destinations = {destination for _, destination in backups}
        # Rollback is best-effort: record each helper failure and keep restoring the closure.
        for destination in reversed(installed):
            try:
                remove_file(destination)
            except Exception as error:  # noqa: BLE001
                if destination not in backed_up_destinations:
                    rollback_errors.append(f"remove {destination}: {error}")
        for backup, destination in reversed(backups):
            if not backup.exists():
                continue
            try:
                replace_path(backup, destination)
            except Exception as error:  # noqa: BLE001
                rollback_errors.append(f"restore {destination} from {backup}: {error}")
        if rollback_errors:
            preserved = [str(backup) for backup, _ in backups if backup.exists()]
            details = "; ".join(rollback_errors)
            raise RuntimeError(
                "artifact publication failed and rollback was incomplete; "
                f"preserved backups={preserved}: {details}"
            ) from publication_error
        raise

    for backup, _ in backups:
        if not backup.exists():
            continue
        try:
            remove_file(backup)
        except OSError as error:
            warnings.warn(
                f"published artifact closure but could not remove backup {backup}: {error}",
                RuntimeWarning,
                stacklevel=2,
            )


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent, text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        publish_artifact_closure([(temporary, path)])
    finally:
        temporary.unlink(missing_ok=True)
