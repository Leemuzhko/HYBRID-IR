"""Portable discovery for TI C6000 Code Generation Tools."""

from __future__ import annotations

import os
from pathlib import Path


def find_ti_root(repo_root: Path) -> Path:
    candidates: list[Path] = []

    configured = os.environ.get("ZOOM_TI_ROOT")
    if configured:
        candidates.append(Path(configured))

    toolchain_name = "ti-cgt-c6000_8.5.0.LTS"
    candidates.append(repo_root.parent / toolchain_name)
    for ancestor in (repo_root, *repo_root.parents):
        candidates.append(ancestor / "tools" / toolchain_name)
    candidates.append(
        Path(
            "/Applications/ti/ccs2050/ccs/tools/compiler/"
            "ti-cgt-c6000_8.5.0.LTS"
        )
    )

    executable_names = ("cl6x.exe", "cl6x")
    checked_candidates: list[Path] = []
    for candidate in candidates:
        if candidate in checked_candidates:
            continue
        checked_candidates.append(candidate)
        if any((candidate / "bin" / name).is_file() for name in executable_names):
            return candidate.resolve()

    checked = "\n".join(f"  - {path}" for path in checked_candidates)
    raise FileNotFoundError(
        "TI C6000 CGT was not found. Set ZOOM_TI_ROOT to the compiler root.\n"
        f"Checked:\n{checked}"
    )


def ti_executable(ti_root: Path, name: str) -> Path:
    for filename in (f"{name}.exe", name):
        path = ti_root / "bin" / filename
        if path.is_file():
            return path
    raise FileNotFoundError(f"{name} not found under {ti_root / 'bin'}")
