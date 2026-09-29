"""Plan completely in memory, then publish through the existing package transaction."""
import copy
import json
import struct
from dataclasses import dataclass, replace
from pathlib import Path
from .bank_prepare import prepare_bank
from .template_profile import load_package, sha, inspect_template
from .zoom_variable_patch import section_usage
from .zoom_budget import picture_bytes
from .zoom_bank import pack_bank, identity_conflicts, catalog_entries
from .zoom_export import check_package_paths, publish_package


def _pack(project,profile):
    if profile['codec']=='HVB4':
        from .zoom_rbj_bank import pack
        return pack(project)
    return pack_bank(project,capacity=profile['capacity'],binary=True)


@dataclass(frozen=True)
class PatchPlan:
    project: object
    raw: bytes
    image_png: bytes
    report: dict


def plan_patch(project,package,*,mode='preserve',taps=None):
    """No output, subprocess, fitting, or authoring mutation. No hardware verdict."""
    from PIL import Image
    import io
    from .template_profile import validate_profile
    profile=copy.deepcopy(package.profile)
    validate_profile(profile,package.raw)
    prepared,conversion=prepare_bank(project,package.model_target,mode=mode,taps=taps)
    prepared.validate()
    bank,report=_pack(prepared,profile)
    picture=picture_bytes(prepared.image)
    with Image.open(prepared.image) as im:
        image=io.BytesIO();im.convert('L').save(image,format='PNG')
    if profile['backend']=='hvb4-tail/1':
        from .zoom_variable_repack import repack_roles
        raw,details=repack_roles(package.raw,bank,expected_sha256=profile['sha256'])
        # Resolve bindings after relocation, never reuse stale file offsets.
        bindings=inspect_template(raw,profile['backend'])['bindings']
    else:
        raw=package.raw;details={};bindings=profile['bindings']
    patches=dict(name=prepared.name.encode('ascii'),id=struct.pack('<H',prepared.fxid),
                 ir_a_max=struct.pack('<I',len(prepared.slots)),
                 ir_b_max=struct.pack('<I',len(prepared.slots)),image=picture)
    if profile['backend']=='irb2-fixed/1':patches['bank']=bank
    result=bytearray(raw)
    for key,data in patches.items():
        at,size=bindings[key]
        if len(data)>size or (key=='bank' and len(data)!=size):raise ValueError('Template capacity exceeded: '+key)
        result[at:at+size]=data.ljust(size,b'\0')
    result=bytes(result)
    usage=section_usage(result)
    if usage['code_const_bytes']>profile['limits']['code_const_bytes']:
        raise ValueError('Bank exceeds template code + const loading profile')
    for name,size in profile['sections'].items():
        if name!='.const' and usage['sections'][name]!=size:
            raise ValueError('Unexpected section size change: '+name)
    # Fixed ABI permits only declared spans; variable backend owns complete fixups.
    if profile['backend']=='irb2-fixed/1':
        cursor=0
        for at,size in sorted(bindings.values()):
            if result[cursor:at]!=package.raw[cursor:at]:raise ValueError('Unexpected fixed template change')
            cursor=at+size
        if result[cursor:]!=package.raw[cursor:]:raise ValueError('Unexpected fixed template tail change')
    report.update(details,**usage,schema='hybrid-template-export/1',sha256=sha(result),
                  template_sha256=profile['sha256'],passport_sha256=sha(json.dumps(profile,sort_keys=True).encode()),
                  backend=profile['backend'],codec=profile['codec'],preparation=conversion,
                  template_acceptance=profile['acceptance'],compiler_used=False,hardware_validated=False,
                  code_and_relocations_unchanged=profile['backend']=='irb2-fixed/1',
                  warning='Host-validated package only. Neither passport nor byte cap guarantees pedal operation.')
    return PatchPlan(prepared,result,image.getvalue(),report)


def bank_usage(project,package):
    """Use the same packer/target as export. Over-capacity plans fail before writes."""
    # Budget checks inspect models only; do not clone full source audio on a timer.
    p=replace(project,name='HYBRID IR',filename='HYBRIDIR',fxid=565,
              slots=[replace(slot,session=None) for slot in project.slots])
    if p.slots:
        prepared,_=prepare_bank(p,package.model_target)
        bank,report=_pack(prepared,package.profile)
    else:
        # An empty authoring bank is valid, but is not an exportable ZDL.
        # Do not fabricate a slot or relax the export packer's validation.
        p.validate(allow_empty=True)
        bank=b''
        report=dict(bank_bytes=0, fir_pool_samples=0, bq_pool_sections=0,
                    max_fir=0, max_bq=0, empty_authoring_bank=True)
    profile=package.profile
    cap=profile['capacity']
    code=profile['sections']['.text']+profile['sections']['.audio']
    used=(profile['const_prefix']+(len(bank)+7)//8*8 if profile['backend']=='hvb4-tail/1'
          else profile['sections']['.const'])
    budget=profile['limits']['code_const_bytes']-code
    image=len(picture_bytes(project.image))
    limits=dict(slots=(len(project.slots),cap['entry_count']-1),fir_pool=(report['fir_pool_samples'],cap['fir_pool_samples']),
                bq_pool=(report['bq_pool_sections'],cap['bq_pool_sections']),max_fir=(report['max_fir'],cap['max_fir']),
                max_bq=(report['max_bq'],cap['max_bq']),image=(image,profile['bindings']['image'][1]))
    return dict(report,const_bytes=used,const_budget=budget,remaining_bytes=budget-used,active_slots=len(project.slots),
                code_const_bytes=code+used,code_const_cap=profile['limits']['code_const_bytes'],limits=limits,
                rbj_parameter_bytes=report.get('rbj_parameter_bytes',0),common_pres_parameter_bytes=report.get('common_pres_parameter_bytes',0),
                gain_lut_bytes=report.get('gain_lut_bytes',0),template_fits=bool(project.slots) and used<=budget and all(a<=b for a,b in limits.values()))


def patch_project(project,output,overwrite=False,allow_identity_replace=False,*,profile_path,
                  allow_experimental=False,mode='preserve',taps=None):
    package=load_package(profile_path)
    package.require_export_consent(allow_experimental)
    plan=plan_patch(project,package,mode=mode,taps=taps)
    return publish_plan(plan,package,output,overwrite,allow_identity_replace,allow_experimental=allow_experimental)


def publish_plan(plan,package,output,overwrite=False,allow_identity_replace=False,*,allow_experimental=False):
    """Publish the exact in-memory artifact the UI previewed and confirmed."""
    package.require_export_consent(allow_experimental)
    project=plan.project
    project.validate()
    if sha(plan.raw)!=plan.report['sha256'] or package.profile['sha256']!=plan.report['template_sha256']:
        raise ValueError('Export plan integrity mismatch')
    paths=check_package_paths(project,output,overwrite)
    protected={package.binary_path,package.profile_path}
    if any(p.resolve() in protected for p in paths.values()):raise ValueError('Cannot overwrite template package')
    conflicts=identity_conflicts(project)
    if conflicts and not allow_identity_replace:raise ValueError('ID occupied; choose a free ID or confirm replacement')
    if conflicts and any(e['name']!=project.name for e in catalog_entries(project) if e['path'] in conflicts):
        raise ValueError('Occupied ID has a different/unknown name; choose a free ID')
    return publish_package(plan.project,output,plan.raw,plan.image_png,plan.report,overwrite),plan.report


def main():
    import argparse,json
    from .zoom_bank import BankProject
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bank',type=Path)
    parser.add_argument('--template',type=Path,required=True,help='Companion .template.json, not an arbitrary ZDL')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--allow-experimental',action='store_true')
    parser.add_argument('--mode',choices=['preserve','bake','original'],default='preserve')
    parser.add_argument('--taps',type=int)
    parser.add_argument('--overwrite',action='store_true')
    args=parser.parse_args()
    path,report=patch_project(BankProject.load(args.bank),args.output,args.overwrite,profile_path=args.template,
                             allow_experimental=args.allow_experimental,mode=args.mode,taps=args.taps)
    print(json.dumps(dict(path=str(path),report=report),indent=2))


if __name__=='__main__':main()
