from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path


def run_checked(
    args: Sequence[str | os.PathLike[str]], *, cwd: Path | None = None
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run([str(arg) for arg in args], cwd=cwd, check=True)
