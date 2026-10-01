"""Read-only deployment gate. Load-command floors are not old-OS runtime proof.

Mach-O constants/layout: apple-oss-distributions/xnu EXTERNAL_HEADERS/mach-o/.
Never lower load commands to make an incompatible binary appear compatible.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import plistlib
import struct

CPU = {'arm64': 0x0100000C, 'x86_64': 0x01000007}
THIN = {b'\xce\xfa\xed\xfe': ('<', 28), b'\xcf\xfa\xed\xfe': ('<', 32),
        b'\xfe\xed\xfa\xce': ('>', 28), b'\xfe\xed\xfa\xcf': ('>', 32)}
FAT = {b'\xca\xfe\xba\xbe': ('>', False), b'\xbe\xba\xfe\xca': ('<', False),
       b'\xca\xfe\xba\xbf': ('>', True), b'\xbf\xba\xfe\xca': ('<', True)}
DYLIB_LOADS = {0xC, 0x80000018, 0x8000001F, 0x20, 0x80000023}


def version(text: str) -> tuple[int, int, int]:
    parts = str(text).split('.')
    if not 1 <= len(parts) <= 3 or any(not p.isdigit() for p in parts):
        raise ValueError('Invalid macOS version: ' + str(text))
    return tuple((list(map(int, parts)) + [0, 0])[:3])


def packed_version(number: int) -> str:
    return f'{number >> 16}.{(number >> 8) & 255}.{number & 255}'


def parse_macho(raw: bytes, nested=False) -> list[dict]:
    magic = raw[:4]
    if magic in FAT:
        if nested or len(raw) < 8:
            raise ValueError('Invalid nested/truncated fat Mach-O')
        endian, wide = FAT[magic]
        count = struct.unpack_from(endian + 'I', raw, 4)[0]
        size = 32 if wide else 20
        table_end = 8 + count * size
        if not 0 < count <= 32 or table_end > len(raw):
            raise ValueError('Invalid fat Mach-O table')
        results, extents = [], []
        for i in range(count):
            start = 8 + i * size
            cpu = struct.unpack_from(endian + 'I', raw, start)[0]
            offset, length = struct.unpack_from(endian + ('QQ' if wide else 'II'), raw, start + 8)
            if length < 28 or offset < table_end or offset + length > len(raw):
                raise ValueError('Invalid fat Mach-O slice bounds')
            if any(offset < end and begin < offset + length for begin, end in extents):
                raise ValueError('Overlapping Mach-O slices')
            extents.append((offset, offset + length))
            part = parse_macho(raw[offset:offset + length], nested=True)
            if len(part) != 1 or part[0]['cpu'] != cpu:
                raise ValueError('Fat architecture table does not match its slice')
            results.extend(part)
        return results
    if magic not in THIN:
        return []
    endian, header_size = THIN[magic]
    if len(raw) < header_size:
        raise ValueError('Truncated Mach-O header')
    cpu, _, _, count, commands_size = struct.unpack_from(endian + 'IIIII', raw, 4)
    end = header_size + commands_size
    if end > len(raw) or count > commands_size // 8:
        raise ValueError('Invalid Mach-O command table')
    offset, floors, dependencies, rpaths = header_size, [], [], []
    for _ in range(count):
        if offset + 8 > end:
            raise ValueError('Truncated Mach-O command')
        command, size = struct.unpack_from(endian + 'II', raw, offset)
        if size < 8 or size % 4 or offset + size > end:
            raise ValueError('Invalid Mach-O command bounds')
        if command == 0x32:
            if size < 24:
                raise ValueError('Truncated LC_BUILD_VERSION')
            platform, minimum, sdk, tools = struct.unpack_from(endian + 'IIII', raw, offset + 8)
            if platform != 1 or 24 + tools * 8 > size:
                raise ValueError('Non-macOS platform or malformed build-version tools')
            floors.append((minimum, sdk))
        elif command == 0x24:
            if size < 16:
                raise ValueError('Truncated LC_VERSION_MIN_MACOSX')
            floors.append(struct.unpack_from(endian + 'II', raw, offset + 8))
        elif command in (0x25, 0x2F, 0x30):
            raise ValueError('Non-macOS minimum-version command')
        elif command in DYLIB_LOADS or command == 0x8000001C:
            minimum_size = 12 if command == 0x8000001C else 24
            if size < minimum_size:
                raise ValueError('Truncated dylib/rpath command')
            position = struct.unpack_from(endian + 'I', raw, offset + 8)[0]
            if not minimum_size <= position < size:
                raise ValueError('Invalid dylib/rpath string offset')
            string = raw[offset + position:offset + size]
            if b'\0' not in string:
                raise ValueError('Unterminated dylib/rpath string')
            text = string.split(b'\0', 1)[0].decode('utf-8')
            (rpaths if command == 0x8000001C else dependencies).append(text)
        offset += size
    if offset != end:
        raise ValueError('Mach-O command count/size mismatch')
    return [dict(cpu=cpu, minimum_macos=packed_version(max(f[0] for f in floors)) if floors else None,
                 sdk=packed_version(max(f[1] for f in floors)) if floors else None,
                 dependencies=dependencies, rpaths=rpaths)]


def audit(app: Path, minimum: str, arch: str) -> dict:
    app = app.resolve(strict=True)
    target = version(minimum)
    if arch not in CPU:
        raise ValueError('Unsupported target architecture')
    errors, files = [], []
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    declared = info.get('LSMinimumSystemVersion')
    if declared is None or version(declared) != target:
        errors.append('Info.plist minimum does not match the requested target')
    for path in sorted(app.rglob('*')):
        relative = path.relative_to(app).as_posix()
        if path.is_symlink():
            try:
                if not path.resolve(strict=True).is_relative_to(app):
                    errors.append(relative + ': external bundle symlink')
            except (OSError, RuntimeError):
                errors.append(relative + ': broken bundle symlink')
            continue
        if not path.is_file():
            continue
        with path.open('rb') as stream:
            magic = stream.read(4)
            if magic not in THIN and magic not in FAT:
                if path.suffix in ('.so', '.dylib'):
                    errors.append(relative + ': expected a Mach-O runtime binary')
                continue
            raw = magic + stream.read()
        try:
            slices = parse_macho(raw)
            selected = [row for row in slices if row['cpu'] == CPU[arch]]
            if len(selected) != 1:
                raise ValueError('Missing or duplicate target architecture')
            row = selected[0]
            if row['minimum_macos'] is None:
                raise ValueError('No minimum macOS load command')
            if version(row['minimum_macos']) > target:
                errors.append(relative + ': requires macOS ' + row['minimum_macos'])
            for dep in row['dependencies'] + row['rpaths']:
                if dep.startswith('/') and not dep.startswith(('/System/Library/', '/usr/lib/')):
                    errors.append(relative + ': non-relocatable external runtime path: ' + dep)
            files.append(dict(path=relative, **row))
        except (ValueError, struct.error, UnicodeError) as error:
            errors.append(relative + ': ' + str(error))
    if not files:
        errors.append('No runtime Mach-O files found')
    executable = 'Contents/MacOS/' + info.get('CFBundleExecutable', '')
    if not any(row['path'] == executable for row in files):
        errors.append('Bundle executable missing from the binary audit')
    return dict(schema='hybridir-macos-deployment-audit/1', success=not errors,
                target_macos=minimum, architecture=arch, declared_minimum=declared,
                maximum_binary_minimum=max((row['minimum_macos'] for row in files), key=version, default=None),
                binary_count=len(files), errors=errors, files=files,
                runtime_test_on_target=False,
                limitations='Static headers and absolute runtime paths only; does not prove symbol availability, weak-import handling or execution on an older OS.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--minimum', required=True)
    parser.add_argument('--arch', choices=CPU, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.app, args.minimum, args.arch)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}, indent=2))
    raise SystemExit(0 if result['success'] else 1)
