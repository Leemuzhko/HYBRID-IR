"""Declarative, hash-paired passports for explicitly supported SDK data ABIs.

No executable JSON, arbitrary relocations, or universal hardware size claim.
Addresses are verified against final ELF symbols and bank headers on every load.
"""
import hashlib
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from .bank_prepare import TargetModel
from .zoom_variable_patch import symbol, section_usage
from .zoom_variable_repack import layout

SCHEMA='hybrid-zdl-template/1'
TARGET='zoom-zdl-c674x-elf32-le-sdk13/1'
BACKENDS={'hvb4-tail/1':'HVB4','irb2-fixed/1':'IRB2'}
FAILED_HASHES={
    'a65250657b900f3856f18a7e3b54ef45756adbe4408b2b1355d3977fcc06dcd0':
    'HOBASE/HOFOUR2K: slot-insertion hang; see ZDL_KNOWN_FAILURES_RU.md'
}


def sha(raw):return hashlib.sha256(raw).hexdigest()


def inspect_template(raw, backend):
    """SDK-specific annotation resolver; not a decoder for arbitrary ZDL files."""
    if backend not in BACKENDS:raise ValueError('Unsupported template backend')
    elf,_,_,_,sections=layout(raw)
    desc,desc_size=symbol(raw,'SonicStomp')
    if desc_size!=11*48:raise ValueError('Unsupported descriptor ABI')
    selectors=[]
    for i in range(2,11):
        at=desc+48*i
        if raw[at:at+12].split(b'\0')[0] in (b'IR-L',b'IR-R'):selectors.append([at+12,4])
    if len(selectors)!=2:raise ValueError('Expected two IR selectors')
    const=sections['.const'][1]
    data=elf[const[4]:const[4]+const[5]]
    magic=BACKENDS[backend].encode('ascii')
    if data.count(magic)!=1:raise ValueError('Ambiguous bank anchor')
    start=76+const[4]+data.index(magic)
    if backend=='hvb4-tail/1':
        from .zoom_rbj_bank import validate
        size=struct.unpack_from('<I',raw,start+8)[0]
        validate(raw[start:start+size])
        capacity=dict(entry_count=9,max_fir=4096,max_bq=32,fir_pool_samples=65534,bq_pool_sections=65535)
        from .zoom_variable_repack import repack_roles
        repack_roles(raw,raw[start:start+size],expected_sha256=sha(raw))
    else:
        header=struct.unpack_from('<IHHHHBBHHHHHII',raw,start)
        _,version,hs,count,fir,bq,label,flags,fp,bp,ds,steps,size,reserved=header
        if (version,hs,label,flags,ds,steps,reserved)!=(1,32,8,1,48,61,0):
            raise ValueError('Unsupported IRB2 bank header')
        capacity=dict(entry_count=count,max_fir=fir,max_bq=bq,fir_pool_samples=fp,bq_pool_sections=bp)
        # Encoder checks numeric capacity bounds and the exact serialized extent.
        import numpy as np
        from .zoom_bank import BankProject,Slot,pack_bank
        from .dsp import Model
        probe,_=pack_bank(BankProject(slots=[Slot('UNIT',Model(44100,np.r_[1.,np.zeros(31)],[]))]),capacity=capacity,binary=True)
        if len(probe)!=size:raise ValueError('Invalid fixed bank extent')
    bindings=dict(bank=[start,size],name=[desc+48,12],id=[64,2],
                  ir_a_max=selectors[0],ir_b_max=selectors[1],image=list(symbol(raw,'picEffectType_HYBRID IR')))
    spans=[]
    for key,(at,n) in bindings.items():
        if n<=0 or at<0 or at+n>len(raw) or any(at<end and begin<at+n for begin,end in spans):
            raise ValueError('Overlapping/out-of-bounds template bindings')
        if key!='id' and not 76+const[4]<=at<at+n<=76+const[4]+const[5]:
            raise ValueError('Writable binding outside .const')
        spans.append((at,at+n))
    return dict(bindings=bindings,capacity=capacity,const_prefix=start-76-const[4],
                sections=section_usage(raw)['sections'])


def make_profile(raw, filename, *, backend, code_const_cap, provenance):
    """Called after final linking by a developer builder, never guessed by end users."""
    facts=inspect_template(raw,backend)
    profile=dict(schema=SCHEMA,target=TARGET,backend=backend,codec=BACKENDS[backend],
                 binary=filename,sha256=sha(raw),**facts,
                 limits=dict(code_const_bytes=code_const_cap,fardata_bytes=facts['sections']['.fardata']),
                 acceptance=dict(status='unverified',evidence=[]),provenance=provenance)
    validate_profile(profile,raw)
    return profile


def validate_profile(profile,raw):
    required={'schema','target','backend','codec','binary','sha256','bindings','capacity','const_prefix','sections','limits','acceptance','provenance'}
    if set(profile)!=required or profile['schema']!=SCHEMA or profile['target']!=TARGET:
        raise ValueError('Unsupported template profile schema/target/fields')
    if profile['backend'] not in BACKENDS or profile['codec']!=BACKENDS[profile['backend']]:
        raise ValueError('Unsupported template codec/backend')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.[zZ][dD][lL]',profile['binary']):
        raise ValueError('Template binary must be a sibling basename')
    if sha(raw)!=profile['sha256']:raise ValueError('Template SHA256 mismatch')
    expected=inspect_template(raw,profile['backend'])
    if any(profile[k]!=v for k,v in expected.items()):
        raise ValueError('Template profile disagrees with final ELF/bank bindings')
    limits=profile['limits']
    if set(limits)!={'code_const_bytes','fardata_bytes'} or any(type(v) is not int or not 0<v<=1_048_576 for v in limits.values()):
        raise ValueError('Invalid loading profile limits')
    if limits['fardata_bytes']!=expected['sections']['.fardata']:
        raise ValueError('State capacity must match compiled template')
    acceptance=profile['acceptance']
    if set(acceptance)!={'status','evidence'} or acceptance['status'] not in ('unverified','historical-pass','failed') or not isinstance(acceptance['evidence'],list):
        raise ValueError('Invalid template acceptance metadata')
    if not isinstance(profile['provenance'],str):raise ValueError('Invalid provenance')


@dataclass(frozen=True)
class TemplatePackage:
    profile: dict
    raw: bytes
    profile_path: Path
    binary_path: Path

    @property
    def model_target(self):
        return TargetModel(max_fir=self.profile['capacity']['max_fir'],
                           trained_reso=self.profile['codec']=='HVB4')

    def require_export_consent(self,allow_experimental):
        failure=FAILED_HASHES.get(self.profile['sha256'])
        if failure or self.profile['acceptance']['status']=='failed':
            raise ValueError('Known failed template: '+(failure or 'developer marked failed'))
        if not allow_experimental:
            raise ValueError('Explicit experimental-template confirmation required; passport is not hardware validation')


def load_package(path):
    path=Path(path).resolve()
    if path.stat().st_size>64_000:raise ValueError('Template profile is too large')
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise ValueError('Duplicate template profile key')
            out[k]=v
        return out
    profile=json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=unique)
    filename=profile.get('binary','')
    if not isinstance(filename,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+\.[zZ][dD][lL]',filename):
        raise ValueError('Template binary must be a sibling basename')
    binary=path.parent/filename
    if binary.is_symlink() or binary.stat().st_size>1_048_576:raise ValueError('Unsafe/oversize template binary')
    raw=binary.read_bytes()
    validate_profile(profile,raw)
    return TemplatePackage(profile,raw,path,binary.resolve())
