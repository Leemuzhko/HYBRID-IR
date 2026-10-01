"""Read and verify the exact lower-deployment-target wheels, never just versions."""
from __future__ import annotations
import importlib.metadata
import json
from pathlib import Path
import platform
import re
from urllib.parse import unquote, urlsplit


def locked_wheels(path: Path, arch: str) -> dict:
    from packaging.tags import mac_platforms, cpython_tags, compatible_tags
    from packaging.utils import canonicalize_name, parse_wheel_filename
    if arch not in ('arm64', 'x86_64'):
        raise ValueError('Unsupported architecture')
    platforms = list(mac_platforms((12, 0), arch))
    compatible = set(cpython_tags((3, 14), abis=['cp314'], platforms=platforms))
    compatible.update(compatible_tags((3, 14), interpreter='cp314', platforms=platforms))
    result = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([a-z0-9_-]+) @ (https://files\.pythonhosted\.org/\S+\.whl) --hash=sha256:([a-f0-9]{64})', line)
        if not match:
            raise ValueError('Expected one exact PyPI wheel URL and SHA256 per line')
        name, url, sha = match.groups()
        name = canonicalize_name(name)
        filename = unquote(Path(urlsplit(url).path).name)
        wheel_name, version, _, tags = parse_wheel_filename(filename)
        if name in result or name != canonicalize_name(wheel_name):
            raise ValueError('Duplicate or mismatched wheel name: ' + name)
        if not tags & compatible:
            raise ValueError('Wheel does not target CPython 3.14 / macOS 12 / ' + arch + ': ' + filename)
        result[name] = dict(version=str(version), url=url, sha256=sha, filename=filename)
    if not result:
        raise ValueError('Empty compatibility wheel lock')
    return result


def verify_environment(root: Path, arch: str) -> dict:
    if platform.python_implementation() != 'CPython' or platform.python_version() != '3.14.6':
        raise ValueError('Compatibility build requires CPython 3.14.6; runtime licenses are pinned to it')
    records = locked_wheels(root / 'packaging/macos/compat' / ('requirements-' + arch + '.txt'), arch)
    installed = {re.sub(r'[-_.]+', '-', d.metadata['Name']).lower()
                 for d in importlib.metadata.distributions() if d.metadata.get('Name')}
    if installed != set(records):
        raise ValueError('Use a clean compatibility venv; unexpected/missing distributions: ' + str(installed ^ set(records)))
    for name, row in records.items():
        distribution = importlib.metadata.distribution(name)
        if distribution.version != row['version']:
            raise ValueError('Compatibility dependency version mismatch: ' + name)
        direct = json.loads(distribution.read_text('direct_url.json') or '{}')
        hashes = direct.get('archive_info', {}).get('hashes', {})
        if direct.get('url') != row['url'] or hashes.get('sha256') != row['sha256']:
            raise ValueError('Install the exact hash-locked compatibility wheel, not a newer-platform variant: ' + name)
    return records
