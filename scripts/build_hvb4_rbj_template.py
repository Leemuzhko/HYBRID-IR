"""Build a synthetic HVB4 RBJ template; never reads user IRs or rewrites exports."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'hybridir_sdk'))
sys.path.insert(0, str(ROOT/'irbq_lab'))
from sdk.build_effect import build_effect
from irbq.dsp import Model
from irbq.zoom_bank import BankProject, Slot
from irbq.zoom_rbj_bank import pack, validate


def bank_header(bank):
    report = validate(bank)
    words = struct.unpack('<'+'I'*(len(bank)//4), bank)
    inverse = struct.unpack('<I', struct.pack('<f', 1/(report['entry_count']-1)))[0]
    return '''#include <stdint.h>
#ifdef __TI_COMPILER_VERSION__
#pragma DATA_SECTION(gj_bank_meta, ".const:gjmeta")
#pragma DATA_SECTION(gj_bank, ".const:gjbank")
#pragma DATA_ALIGN(gj_bank, 8)
#endif
#ifdef GJ_HOST_BANK
static const uint32_t *gj_bank;
static volatile uint32_t gj_bank_meta[3];
#else
const volatile uint32_t gj_bank_meta[3]={0x344d4248u,%du,%du};
const volatile uint32_t gj_bank[%d]={%s};
#endif
#include "../bank_v4.h"
''' % (len(bank), inverse, len(words), ','.join(hex(w)+'u' for w in words))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Fresh output required')
    stage = args.output/'source'
    shutil.copytree(ROOT/'hybridir_sdk/src/custom/hybridir_roles', stage)
    bank, _ = pack(BankProject(slots=[Slot('UNIT', Model(44100, np.r_[.5,np.zeros(31)], []))]))
    (stage/'generated/bank_u1.h').write_text(bank_header(bank), encoding='utf-8')
    manifest = json.loads((stage/'manifest.json').read_text(encoding='utf-8'))
    manifest.update(fxid=740, output_basename='HRBASE')
    (stage/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    result = build_effect(stage, ROOT/'hybridir_sdk', output_dir=args.output/'build')
    from emit_template_profile import emit
    emit(result.zdl_path,backend='hvb4-tail/1',code_const_cap=28904,
         provenance='Developer SDK build; synthetic UNIT; unverified artifact. See THIRD_PARTY_NOTICES.md.')
    print(result.zdl_path)


if __name__ == '__main__':
    main()
