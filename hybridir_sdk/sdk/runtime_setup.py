"""Provision exact runtime bytes from user-owned inputs; never download firmware."""
from __future__ import annotations
import hashlib
from pathlib import Path
import subprocess

# Verified against the active HYBRIDIR linker. Offsets are in whole ZDL files.
# Full donor hashes are evidence; an identical fragment at the same offset is
# accepted under another stock filename/header. Output bytes must match exactly.
RECIPES = {
    'linesel_handlers.bin': {
        'donor':'MS-70CDR_LINESEL.ZDL', 'offset':0x8c, 'size':480,
        'sha256':'ddd2d9545d22603c5f8451c23cf2a89698f2e5076c66e93fcd73063696f5f411',
        'donor_sha256':'3773f220e5d8b4b7994a9bfd613f119471ae3b8d7085e161a027a4b602409be8'},
    'divf_rts.bin': {
        'donor':'ANA234CH.ZDL', 'offset':0x134c, 'size':640,
        'sha256':'0215dfbb454ef9ea68521611d5643dac77df81ccda86f3f189c12c4a8a31424f',
        'donor_sha256':'dedf39cecd6b4c00e65ce805776d0c7605f0894ed4aa1b13eb9a600f57091b7b'},
    'c6xabi_attributes.bin': {
        'donor':'MS-70CDR_EXCITER.ZDL', 'offset':0x125a, 'size':62,
        'sha256':'9d30bec3988860a7d0fec81384f5b771ea6eb4f7a8c0f8eabb1e7c17468625e6',
        'donor_sha256':'079a5cd4ba9c01d21fe03b15df0214c427c084b5aa376e01a4eeed49d29d8aac'},
}

def matches(data, recipe):
    return len(data) == recipe['size'] and hashlib.sha256(data).hexdigest() == recipe['sha256']

def check_compiler(folder):
    if not str(folder).strip():
        raise ValueError('Select the TI C6000 CGT 8.5.0.LTS installation folder.')
    root = Path(folder).resolve()
    if root.name.casefold() == 'bin':
        root = root.parent
    compiler = next((root/'bin'/name for name in ('cl6x.exe','cl6x')
                     if (root/'bin'/name).is_file()), None)
    if compiler is None:
        raise ValueError('TI compiler not found. Select the folder containing bin/cl6x.exe.')
    if not (root/'include'/'stdint.h').is_file():
        raise ValueError('TI compiler headers are missing; complete the TI installation.')
    revision = subprocess.run([str(compiler),'--compiler_revision'], capture_output=True,
                              text=True, check=True, timeout=15).stdout.strip()
    if revision != '8.5.0':
        raise ValueError('This package requires TI C6000 CGT 8.5.0.LTS; selected compiler reports '+revision)
    return root

def collect_runtime(folder):
    if not str(folder).strip() or not Path(folder).is_dir():
        raise ValueError('Select a stock ZDL folder containing LineSel, ANA234CH and Exciter.')
    root = Path(folder).resolve()
    found = {}
    for name, recipe in RECIPES.items():
        for file in (root/name, root/'build'/name):
            if file.is_file() and not file.is_symlink() and file.stat().st_size == recipe['size']:
                data = file.read_bytes()
                if matches(data, recipe):
                    found[name] = {'data':data, 'source':file.name, 'kind':'verified-runtime'}
                    break
    if len(found) < len(RECIPES):
        count = 0
        total_bytes = 0
        for file in root.rglob('*'):
            if file.suffix.casefold() != '.zdl' or not file.is_file():
                continue
            count += 1
            if count > 4096:
                raise ValueError('Too many ZDL files; select a smaller stock-effects folder.')
            size = file.stat().st_size
            if file.is_symlink() or not file.resolve().is_relative_to(root) or size > 4*1024*1024:
                continue
            total_bytes += size
            if total_bytes > 512*1024*1024:
                raise ValueError('Stock scan exceeded 512 MiB; select a smaller folder.')
            raw = file.read_bytes()
            if raw[:8] != b'\0\0\0\0SIZE' or raw[0x4c:0x50] != b'\x7fELF':
                continue
            for name, recipe in RECIPES.items():
                if name in found:
                    continue
                data = raw[recipe['offset']:recipe['offset']+recipe['size']]
                if matches(data, recipe):
                    found[name] = {'data':data, 'source':file.name, 'kind':'stock-zdl-slice',
                                   'offset':recipe['offset'], 'source_sha256':hashlib.sha256(raw).hexdigest()}
            if len(found) == len(RECIPES):
                break
    missing = [recipe['donor'] for name, recipe in RECIPES.items() if name not in found]
    if missing:
        raise ValueError('Matching stock files were not found: '+', '.join(missing)+
                         '. Other versions are accepted only when the runtime bytes match.')
    return found

def write_runtime(sdk, collected):
    if set(collected) != set(RECIPES):
        raise ValueError('Runtime bundle is incomplete')
    for name, recipe in RECIPES.items():
        if not matches(collected[name]['data'], recipe):
            raise ValueError('Runtime validation failed: '+name)
    build = Path(sdk)/'build'
    # Check every destination before writing any file.
    for name, recipe in RECIPES.items():
        target = build/name
        if target.exists() and (target.is_symlink() or not target.is_file()
                                or not matches(target.read_bytes(), recipe)):
            raise ValueError('Existing runtime differs; preserved: '+name)
    build.mkdir(parents=True, exist_ok=True)
    for name, entry in collected.items():
        target = build/name
        if not target.exists():
            with target.open('xb') as stream:
                stream.write(entry['data'])

def verify_runtime(sdk):
    for name, recipe in RECIPES.items():
        path = Path(sdk)/'build'/name
        if not path.is_file() or not matches(path.read_bytes(), recipe):
            raise ValueError('ZDL runtime is not configured. Run HYBRID IR Setup with '
                             'the stock files and TI compiler. Missing or incompatible: '+name)
