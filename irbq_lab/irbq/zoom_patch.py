"""Compiler-free, fixed-layout HYBRID IR patching. No relocation or code edits."""
from pathlib import Path
import hashlib
import json
import io
import struct

from .zoom_bank import SDK, pack_bank, identity_conflicts, catalog_entries
from .zoom_export import check_package_paths, publish_package

TEMPLATES = SDK / 'templates'
PROFILE = TEMPLATES / 'HYBRID4.json'
PROFILE_SHA256 = 'ccaa4990251131b3a3e34c83bdcf33a8e4bf4686086ab193657be61ef44fa066'


def load_template(path=None):
    profile = json.loads(PROFILE.read_text(encoding='utf-8'))
    canonical = json.dumps(profile, sort_keys=True, separators=(',', ':')).encode('utf-8')
    if hashlib.sha256(canonical).hexdigest() != PROFILE_SHA256:
        raise ValueError('Unknown or modified patch template profile')
    if profile.get('schema') != 'hybridir-patch-template/1':
        raise ValueError('Unsupported patch template profile')
    if profile.get('control_tables') != dict(depth=1,presence=1,steps=61):
        raise ValueError('Unsupported control table layout')
    path = Path(path) if path else TEMPLATES / 'HYBRID4.zdl'
    if path.stat().st_size > 1024*1024:
        raise ValueError('Template is too large')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != profile['sha256']:
        raise ValueError('Unknown or modified ZDL template. Use the original HYBRID4 template supplied with this version.')
    off,size = profile['regions']['bank']
    c=profile['capacity']
    expected=struct.pack('<IHHHHBBHHHHHII',0x32425249,1,32,c['entry_count'],c['max_fir'],c['max_bq'],8,1,
                         c['fir_pool_samples'],c['bq_pool_sections'],48,61,size,0)
    if raw[off:off+32] != expected:
        raise ValueError('Template profile disagrees with bank header')
    return path.resolve(), raw, profile


def patch_project(project, output, overwrite=False, allow_identity_replace=False, *, template_path=None):
    """Validate everything before publishing. Template/code/relocations stay intact."""
    project.validate()
    original, raw, profile = load_template(template_path)
    output = Path(output)
    target = output / project.filename / (project.filename + '.zdl')
    if target.resolve() == original or (output / (project.filename + '.zdl')).resolve() == original:
        raise ValueError('The original template must not be overwritten')
    check_package_paths(project, output, overwrite)
    conflicts = identity_conflicts(project)
    if conflicts and not allow_identity_replace:
        raise ValueError('ID occupied; choose a free ID or confirm replacement')
    if conflicts and any(e['name'] != project.name for e in catalog_entries(project) if e['path'] in conflicts):
        raise ValueError('Occupied ID has a different/unknown name; choose a free ID')
    bank, report = pack_bank(project, capacity=profile['capacity'], binary=True)
    # Image encoding uses the same source routine as the compiler-backed builder.
    from PIL import Image
    import sys
    sys.path.insert(0, str(SDK/'build'))
    from screen_image import Canvas, encode_zoom_rle
    with Image.open(project.image) as source:
        image = source.convert('L')
    if image.size != (128,64) or not set(image.tobytes()) <= {0,255}:
        raise ValueError('PNG must contain 128x64 black/white pixels')
    canvas = Canvas()
    canvas.pixels = [[int(image.getpixel((x,y)) == 0) for x in range(128)] for y in range(64)]
    picture = encode_zoom_rle(canvas)
    patches = {
        'bank': bank,
        'name': project.name.encode('ascii'),
        'id': struct.pack('<H',project.fxid),
        'ir_a_max': struct.pack('<I',len(project.slots)),
        'ir_b_max': struct.pack('<I',len(project.slots)),
        'image': picture,
    }
    if set(profile['regions']) != set(patches):
        raise ValueError('Invalid patch profile regions')
    result = bytearray(raw)
    ranges = []
    for key,data in patches.items():
        offset,size = profile['regions'][key]
        if type(offset) is not int or type(size) is not int or offset < 0 or size <= 0 or offset+size > len(raw):
            raise ValueError('Invalid patch region: '+key)
        if len(data) > size or (key == 'bank' and len(data) != size):
            raise ValueError(f'{key} exceeds template capacity ({len(data)} > {size} bytes). Use a simpler image or a larger developer-built template.')
        if any(offset < end and start < offset+size for start,end in ranges):
            raise ValueError('Overlapping patch regions')
        ranges.append((offset,offset+size))
        result[offset:offset+size] = data.ljust(size,b'\0')
    # Enforce the public invariant explicitly, independently of individual writes.
    cursor = 0
    for start,end in sorted(ranges):
        if result[cursor:start] != raw[cursor:start]:raise ValueError('Unexpected template modification')
        cursor = end
    if result[cursor:] != raw[cursor:] or len(result) != len(raw):
        raise ValueError('Unexpected template modification')
    report.update(schema='hybridir-patch-report/1', template_sha256=profile['sha256'],
                  sha256=hashlib.sha256(result).hexdigest(), zdl_bytes=len(result),
                  compiler_used=False, code_and_relocations_unchanged=True,
                  template_version=profile['version'], hardware_validated=False,
                  changed_regions=profile['regions'])
    image_png = io.BytesIO()
    image.save(image_png, format='PNG')
    target = publish_package(project, output, result, image_png.getvalue(), report, overwrite)
    return target, report


def main():
    import argparse
    from .zoom_bank import BankProject
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bank',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--template',type=Path)
    args=parser.parse_args()
    target,report=patch_project(BankProject.load(args.bank),args.output,template_path=args.template)
    print(json.dumps({'path':str(target),'sha256':report['sha256']}))


if __name__ == '__main__':main()
