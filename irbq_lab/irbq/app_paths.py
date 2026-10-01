"""Resource locations and strict output paths for source and frozen applications.

Only exact root-owned Apple system aliases are accepted; arbitrary user links
and junctions remain forbidden. Caller path spelling is preserved.
"""
from __future__ import annotations
import os
from pathlib import Path
import stat
import sys

_SYSTEM_ALIASES = {'/var': '/private/var', '/tmp': '/private/tmp', '/etc': '/private/etc'}


def application_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def macos_support_directory() -> Path:
    return Path.home() / 'Library' / 'Application Support' / 'HYBRID IR'


def macos_cache_directory() -> Path:
    return Path.home() / 'Library' / 'Caches' / 'HYBRID IR'


def _system_alias(path: Path) -> Path | None:
    target = _SYSTEM_ALIASES.get(path.as_posix())
    if sys.platform != 'darwin' or target is None:
        return None
    info = path.lstat()
    if not stat.S_ISLNK(info.st_mode) or info.st_uid != 0:
        return None
    link = os.readlink(path)
    expected = Path(target)
    if link not in (target, target.lstrip('/')):
        return None
    destination = Path(link) if Path(link).is_absolute() else path.parent / link
    if destination != expected or expected.is_symlink() or not expected.is_dir():
        return None
    return expected


def safe_output_directory(value: str | os.PathLike) -> Path:
    """Check before canonicalization can hide a user link; preserve caller spelling.

Apple's root aliases are stable system paths. Every component of their canonical
endpoint is checked too. This is not a hostile-concurrent-replacement defense;
export retains its existing recheck immediately before publishing files.
"""
    original = Path(value)
    absolute = original.absolute()
    if '..' in absolute.parts:
        raise ValueError('Output folder path must not contain parent traversal')
    if sys.platform == 'darwin' and len(absolute.parts) > 1:
        first = Path(absolute.anchor) / absolute.parts[1]
        if first.is_symlink():
            replacement = _system_alias(first)
            if replacement is None:
                raise ValueError('Output folder path must not traverse a link or junction: ' + str(first))
            absolute = replacement.joinpath(*absolute.parts[2:])
    for component in (absolute, *absolute.parents):
        if component.is_symlink() or getattr(component, 'is_junction', lambda: False)():
            raise ValueError('Output folder path must not traverse a link or junction: ' + str(component))
    return original
