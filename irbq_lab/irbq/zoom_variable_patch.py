"""Compiler-free HVB4 candidate with trained RESO and common RBJ PRES.

Not an arbitrary ELF editor. Existing fixed-template patcher remains available.
"""
from dataclasses import replace
import hashlib
import io
import struct
from pathlib import Path

from .zoom_bank import SDK, catalog_entries, identity_conflicts
from .zoom_budget import picture_bytes
from .zoom_export import check_package_paths, publish_package
from .zoom_rbj_bank import pack, validate
from .zoom_variable_repack import layout, repack_roles as repack

TEMPLATE = SDK/'templates/HVB4RBJ.zdl'
TEMPLATE_SHA = 'b21528b5a6444dbe6200cf73b450643da22082c0e865a6c86e4cb4b298357894'
CODE_CONST_CAP = 28904
FARDATA_CAP = 144
CONST_PREFIX = 1672
IMAGE_CAP = 848


def symbol(raw, name):
    elf, _, _, _, sections = layout(raw)
    ds, strings = sections['.dynsym'][1], sections['.dynstr'][1]
    names = elf[strings[4]:strings[4]+strings[5]]
    for at in range(ds[4], ds[4]+ds[5], 16):
        ni, va, size, _, _, _ = struct.unpack_from('<IIIBBH', elf, at)
        if names[ni:names.index(0, ni)].decode('ascii') == name:
            for _, s in sections.values():
                if s[2]&2 and s[3] <= va and va+size <= s[3]+s[5]:
                    return 76+s[4]+va-s[3], size
    raise ValueError('Missing allocated symbol: '+name)


def load_template():
    raw = TEMPLATE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != TEMPLATE_SHA:
        raise ValueError('Unknown or modified HVB4RBJ template')
    return raw


def section_usage(raw):
    elf, po, _, _, names = layout(raw)
    sections = {n:s[5] for n,(_,s) in names.items()}
    loads = [struct.unpack_from('<8I', elf, po+32*i) for i in range(4)]
    return dict(sections=sections, code_const_bytes=sum(sections[n] for n in ('.text','.audio','.const')),
                load_memsz_sum=sum(p[5] for p in loads if p[0]==1),
                service_table_bytes=sum(sections[n] for n in ('.rela.dyn','.dynamic','.dynsym','.dynstr','.hash')))


def enforce_profile(raw, original):
    result, base = section_usage(raw), section_usage(original)
    if result['code_const_bytes'] > CODE_CONST_CAP or result['sections']['.fardata'] > FARDATA_CAP:
        raise ValueError('Bank exceeds conservative HVB4RBJ loading profile')
    for n in ('.text','.audio','.rela.dyn','.rela.plt','.dynamic','.dynsym','.dynstr','.hash','.fardata'):
        if result['sections'][n] != base['sections'][n]:
            raise ValueError('Unexpected section size change: '+n)
    return result


def bank_usage(project):
    # UI preview ignores partially entered effect identity, never changes project.
    if not project.slots:
        from .zoom_bank import Slot
        from .dsp import Model
        import numpy as np
        project = replace(project, slots=[Slot('CAB',Model(44100,np.r_[1.,np.zeros(31)],[]))])
        empty = True
    else:
        empty = False
    bank, report = pack(replace(project,name='HYBRID IR',filename='HYBRIDIR',fxid=565))
    raw = load_template()
    base = section_usage(raw)
    code = base['sections']['.text']+base['sections']['.audio']
    used = CONST_PREFIX+(len(bank)+7)//8*8
    cap = CODE_CONST_CAP-code
    image = len(picture_bytes(project.image))
    limits = dict(slots=(0 if empty else len(project.slots),8),
                  fir_pool=(report['fir_pool_samples'],65534), bq_pool=(report['bq_pool_sections'],65535),
                  max_fir=(report['max_fir'],4096),max_bq=(report['max_bq'],32),image=(image,IMAGE_CAP))
    fraction = max(used/cap, image/IMAGE_CAP)
    return dict(report,const_bytes=used,const_budget=cap,remaining_bytes=cap-used,
                active_slots=0 if empty else len(project.slots),image_bytes=image,
                code_const_bytes=code+used,code_const_cap=CODE_CONST_CAP,
                control_table_bytes=report['control_table_bytes'],limits=limits,template_fraction=fraction,
                template_fits=fraction<=1 and all(a<=b for a,b in limits.values()),hardware_validated=False)


def patch_project(project, output, overwrite=False, allow_identity_replace=False):
    project.validate()
    raw = load_template()
    output = Path(output)
    # Check destinations/identity before publishing; same semantics as fixed path.
    check_package_paths(project, output, overwrite)
    conflicts = identity_conflicts(project)
    if conflicts and not allow_identity_replace:
        raise ValueError('ID occupied; choose a free ID or confirm replacement')
    if conflicts and any(e['name']!=project.name for e in catalog_entries(project) if e['path'] in conflicts):
        raise ValueError('Occupied ID has a different/unknown name; choose a free ID')
    bank, report = pack(project)
    # Resource gate before changing anything or creating output directories.
    usage = bank_usage(project)
    if not usage['template_fits']:
        raise ValueError('Bank/image exceeds conservative HVB4RBJ loading profile')
    result, details = repack(raw,bank,expected_sha256=TEMPLATE_SHA)
    result = bytearray(result)
    desc,_ = symbol(result,'SonicStomp')
    result[desc+48:desc+60] = project.name.encode('ascii').ljust(12,b'\0')
    struct.pack_into('<H', result,64,project.fxid)
    picture = picture_bytes(project.image)
    at,size = symbol(result,'picEffectType_HYBRID IR')
    if size != IMAGE_CAP or len(picture)>size:
        raise ValueError('Card exceeds pinned template image capacity')
    result[at:at+size] = picture.ljust(size,b'\0')
    result = bytes(result)
    actual = enforce_profile(result,raw)
    if actual['code_const_bytes'] != usage['code_const_bytes']:
        raise ValueError('Preview/actual size mismatch')
    report.update(details,**actual,schema='hybridir-variable-patch-report/1',
                  sha256=hashlib.sha256(result).hexdigest(),template_sha256=TEMPLATE_SHA,
                  compiler_used=False,hardware_validated=False,
                  loading_profile='HVB4RBJ-28904-experimental',code_const_cap=CODE_CONST_CAP,
                  instructions_may_change_for_relocation=True,
                  warning='New role/fade kernel needs pedal acceptance; inherited byte cap is not hardware validation')
    from PIL import Image
    image_png = io.BytesIO()
    with Image.open(project.image) as image:
        image.convert('L').save(image_png,format='PNG')
    return publish_package(project,output,result,image_png.getvalue(),report,overwrite),report


def main():
    import argparse
    from .zoom_bank import BankProject
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bank',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    target,report=patch_project(BankProject.load(args.bank),args.output)
    print(target, report['sha256'])


if __name__=='__main__':main()
