import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from irbq.dsp import Model, Biquad
from irbq.zoom_bank import BankProject,Slot,pack_bank
from irbq.zoom_patch import load_template,patch_project


class TestZoomPatch(unittest.TestCase):
    def test_reserved_ids_cannot_be_overridden_and_zem_is_scanned(self):
        from irbq.zoom_bank import identity_conflicts,suggest_free_id
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=self.project();p.fxid=241
            with self.assertRaisesRegex(ValueError,'reserved'):
                patch_project(p,root/'blocked',allow_identity_replace=True)
            self.assertFalse((root/'blocked').exists())
            p=self.project();source,_=patch_project(p,root/'zem'/'nested')
            p.patched_folder=str(root/'zem')
            self.assertEqual(identity_conflicts(p),[str(source)])
            with self.assertRaisesRegex(ValueError,'occupied'):patch_project(p,root/'output')
            p.name='OTHER NAME'
            with self.assertRaisesRegex(ValueError,'different/unknown'):patch_project(p,root/'output',allow_identity_replace=True)
            p.fxid=suggest_free_id(p)
            self.assertNotEqual(p.fxid,567)
            patch_project(p,root/'output')

    def test_profile_integrity_and_formatting(self):
        _,_,profile=load_template()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'profile.json'
            path.write_bytes(json.dumps(profile,indent=4).replace('\n','\r\n').encode('utf-8'))
            with patch('irbq.zoom_patch.PROFILE',path):
                load_template()
                for key,value in (('regions',dict(profile['regions'],name=[100,12])),
                                  ('version','untrusted'),('sha256','0'*64)):
                    path.write_text(json.dumps(dict(profile,**{key:value})),encoding='utf-8')
                    out=Path(td)/'out'
                    with self.assertRaisesRegex(ValueError,'modified patch template profile'):
                        patch_project(self.project(),out)
                    self.assertFalse(out.exists())

    def test_orphan_sidecar_requires_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            sidecar=Path(td)/'PATCHED.patch.json'
            sidecar.write_bytes(b'keep me')
            with self.assertRaises(FileExistsError):patch_project(self.project(),td)
            self.assertEqual(sidecar.read_bytes(),b'keep me')
            self.assertFalse((Path(td)/'PATCHED.zdl').exists())
            target,_=patch_project(self.project(),td,overwrite=True)
            self.assertTrue(target.exists())
            self.assertEqual(json.loads(sidecar.read_text())['schema'],'hybridir-patch-report/1')

    def project(self,n=2,taps=1024):
        return BankProject(name='PATCH TEST',filename='PATCHED',fxid=567,
                           slots=[Slot('CAB'+str(i+1),Model(44100,np.r_[.5,np.zeros(taps-1)],
                               [Biquad(kind='Peak',f=250.,gain=2.)],output_gain_db=-3)) for i in range(n)])

    def test_fixed_bank_and_no_compiler(self):
        _,original,profile=load_template()
        p=self.project()
        with tempfile.TemporaryDirectory() as td, patch('subprocess.run',side_effect=AssertionError('Compiler/process called')), patch.dict(os.environ,{'ZOOM_TI_ROOT':'missing'}):
            target,report=patch_project(p,td)
            raw=target.read_bytes()
            expected,_=pack_bank(p,capacity=profile['capacity'],binary=True)
            off,size=profile['regions']['bank']
            self.assertEqual(raw[off:off+size],expected)
            self.assertEqual(len(raw),len(original))
            self.assertFalse(report['compiler_used'])
            self.assertEqual(struct.unpack_from('<H',raw,64)[0],567)
            for key in ('ir_a_max','ir_b_max'):
                self.assertEqual(struct.unpack_from('<I',raw,profile['regions'][key][0])[0],2)
            mask=bytearray(len(raw))
            for offset,length in profile['regions'].values():mask[offset:offset+length]=b'\1'*length
            self.assertTrue(all(a==b for i,(a,b) in enumerate(zip(raw,original)) if not mask[i]))
            second=Path(td)/'repeat'
            self.assertEqual(patch_project(p,second)[0].read_bytes(),raw)
            self.assertEqual(report['sha256'],hashlib.sha256(raw).hexdigest())

    def test_reject_unknown_template_and_preserve_outputs(self):
        _,raw,_=load_template()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'bad.zdl';path.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
            out=Path(td)/'out'
            with self.assertRaisesRegex(ValueError,'Unknown'):patch_project(self.project(),out,template_path=path)
            self.assertFalse(out.exists())
            path.write_bytes(raw)
            p=self.project();p.filename='bad'
            with self.assertRaisesRegex(ValueError,'original template'):patch_project(p,td,overwrite=True,template_path=path)
            self.assertEqual(path.read_bytes(),raw)
            target,_=patch_project(self.project(),out)
            before=target.read_bytes()
            with self.assertRaises(FileExistsError):patch_project(self.project(),out)
            self.assertEqual(target.read_bytes(),before)

    def test_capacity_errors_and_slot_padding(self):
        _,_,profile=load_template()
        for p in (self.project(5),self.project(1,4096)):
            with self.assertRaisesRegex(ValueError,'capacity'):pack_bank(p,capacity=profile['capacity'],binary=True)
        p=self.project(3,2048)
        for i,s in enumerate(p.slots):s.model.fir[i+1]=.1
        with self.assertRaisesRegex(ValueError,'capacity'):pack_bank(p,capacity=profile['capacity'],binary=True)
        raw,_=pack_bank(self.project(1),capacity=profile['capacity'],binary=True)
        self.assertEqual(raw[32+2*48:32+3*48],raw[32:32+48])
        labels=32+5*48
        self.assertEqual(raw[labels+2*8:labels+3*8],b'EMPTY\0\0\0')

    def test_image_overflow_rejected_without_output(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            rng=np.random.default_rng(7)
            path=Path(td)/'image.png'
            Image.fromarray((rng.integers(0,2,(64,128))*255).astype('uint8')).save(path)
            p=self.project();p.image=str(path)
            out=Path(td)/'out'
            with self.assertRaisesRegex(ValueError,'image exceeds'):patch_project(p,out)
            self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
