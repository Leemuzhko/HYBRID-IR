"""Developer-only: build a synthetic fixed-capacity template with TI, never user IRs."""
from pathlib import Path
import hashlib
import json
import struct
import sys
import argparse
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'irbq_lab'),str(ROOT/'hybridir_sdk/build')]
from irbq.dsp import Model
from irbq.zoom_bank import BankProject,Slot,build_project,pack_bank,atomic_write
from zdl import Zdl
from zdl_smoke import _section_map

CAPACITY = dict(entry_count=5,max_fir=2048,max_bq=32,fir_pool_samples=4096,bq_pool_sections=130)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    project=BankProject(filename='HYBRID4',slots=[Slot('UNIT'+str(i+1),Model(44100,np.r_[1.,np.zeros(31)],[])) for i in range(4)])
    path,report=build_project(project,args.output,capacity=CAPACITY)
    raw=path.read_bytes();elf=Zdl.load(path).elf
    elf_base=len(raw)-len(elf)
    sections=_section_map(elf)
    def section_data(name):
        s=sections[name];return elf[s[4]:s[4]+s[5]]
    names=section_data('.dynstr');symbols={}
    data=section_data('.dynsym')
    for index in range(0,len(data),16):
        name,value,size,info,other,shndx=struct.unpack_from('<IIIBBH',data,index)
        text=names[name:names.index(0,name)].decode('ascii')
        if text:
            for section in sections.values():
                if section[3] <= value < section[3]+section[5] and section[1] != 8:
                    symbols[text]=(elf_base+section[4]+value-section[3],size);break
    bank,_=pack_bank(project,capacity=CAPACITY,binary=True)
    bank_off=raw.find(bank)
    if bank_off<0 or raw.find(bank,bank_off+1)>=0:raise ValueError('Compiled bank does not exactly match Python packing')
    desc,size=symbols['SonicStomp']
    assert size == 11*48 and raw[desc:desc+6] == b'OnOff\0'
    for index in (3,6):
        assert struct.unpack_from('<I',raw,desc+(index+2)*48+12)[0] == 4
    profile=dict(schema='hybridir-patch-template/1',version='hybrid4-v1',
                 sha256=hashlib.sha256(raw).hexdigest(),capacity=CAPACITY,
                 control_tables=dict(depth=1,presence=1,steps=61),
                 provenance='Synthetic unit impulses; compiled HYBRID IR source with inherited stock runtime. See THIRD_PARTY_NOTICES.md.',
                 hardware_validated=False,
                 regions=dict(bank=[bank_off,len(bank)],name=[desc+48,12],id=[64,2],
                              ir_a_max=[desc+5*48+12,4],ir_b_max=[desc+8*48+12,4],
                              image=list(symbols['picEffectType_HYBRID IR'])))
    assert len(raw) == struct.unpack_from('<I',raw,16)[0]+76
    atomic_write(args.output/'HYBRID4.json',json.dumps(profile,indent=2).encode('utf-8'))
    print(json.dumps(profile,indent=2))
    # Review this digest and update zoom_patch.PROFILE_SHA256 when adopting a new template.
    print('Canonical profile SHA256: '+hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest())


if __name__=='__main__':main()
