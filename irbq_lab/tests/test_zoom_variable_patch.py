import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from irbq.dsp import Model
from irbq.zoom_bank import BankProject, Slot
from irbq.zoom_variable_patch import (patch_project,bank_usage,load_template,symbol,
                                     section_usage,enforce_profile,CODE_CONST_CAP)
from irbq.zoom_rbj_bank import validate
from irbq.zoom_variable_repack import layout


class TestVariablePatch(unittest.TestCase):
    def project(self,count=4,taps=64):
        return BankProject(name='SAFE TEST',filename='SAFE',fxid=700,
            slots=[Slot('C'+str(i),Model(44100,np.r_[.5,.001*i,np.zeros(taps-2)],[])) for i in range(count)])

    def test_sizes_identity_and_bank(self):
        import struct
        import hashlib
        for count,taps in ((1,32),(4,256),(8,64),(1,1024)):
            p=self.project(count,taps)
            with tempfile.TemporaryDirectory() as td:
                preview=bank_usage(p)
                target,report=patch_project(p,td)
                raw=target.read_bytes()
                self.assertEqual(report['code_const_bytes'],preview['code_const_bytes'])
                self.assertLessEqual(report['code_const_bytes'],CODE_CONST_CAP)
                self.assertEqual(report['sha256'],hashlib.sha256(raw).hexdigest())
                self.assertFalse(report['compiler_used'])
                at,_=symbol(raw,'SonicStomp')
                self.assertEqual(raw[at+48:at+60].rstrip(b'\0'),b'SAFE TEST')
                self.assertEqual(struct.unpack_from('<H',raw,64)[0],700)
                for i in (6,9):self.assertEqual(struct.unpack_from('<I',raw,at+48*i+12)[0],count)
                self.assertEqual([raw[at+48*i:at+48*i+12].split(b'\0')[0] for i in range(5,11)],
                                 [b'RESO',b'IR-L',b'PRES',b'RESO',b'IR-R',b'PRES'])
                for i in (5,8):self.assertEqual(struct.unpack_from('<I',raw,at+48*i+12)[0],60)
                info,_=symbol(raw,'effectTypeImageInfo')
                self.assertEqual([struct.unpack_from('<I',raw,info+36+16*i)[0] for i in range(6)],
                                 [5,7,2,4,8,10])
                start=raw.index(b'HVB4');size=struct.unpack_from('<I',raw,start+8)[0]
                self.assertEqual(validate(raw[start:start+size])['entry_count'],count+1)
                self.assertEqual(section_usage(raw)['service_table_bytes'],section_usage(load_template())['service_table_bytes'])
                elf,_,_,_,names=layout(raw)
                base,_,_,_,bn=layout(load_template())
                # Code can differ only in relocated references to moved fardata.
                # Existing inverse-roundtrip tests cover those fixups independently.
                self.assertEqual(names['.text'][1][5],bn['.text'][1][5])

    def test_oversize_rejected_without_output(self):
        p=self.project(4,2048)
        self.assertFalse(bank_usage(p)['template_fits'])
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'out'
            with self.assertRaisesRegex(ValueError,'loading profile'):patch_project(p,out)
            self.assertFalse(out.exists())

    def test_profile_rejects_service_and_fardata_growth(self):
        import struct
        raw=load_template()
        _,_,sh,_,names=layout(raw)
        for name in ('.fardata','.dynsym','.dynstr','.hash','.rela.dyn','.dynamic'):
            altered=bytearray(raw)
            index,section=names[name]
            struct.pack_into('<I',altered,76+sh+40*index+20,section[5]+8)
            with self.subTest(section=name):
                with self.assertRaisesRegex(ValueError,'loading profile|section size change'):
                    enforce_profile(bytes(altered),raw)

    def test_template_tamper_no_compiler_and_repeat(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            invalid=root/'bad.zdl';invalid.write_bytes(load_template()+b'bad')
            with patch('irbq.zoom_variable_patch.TEMPLATE',invalid):
                with self.assertRaisesRegex(ValueError,'modified'):patch_project(self.project(),root/'bad')
            with patch('subprocess.run',side_effect=AssertionError('No subprocess')):
                a,_=patch_project(self.project(),root/'a')
                b,_=patch_project(self.project(),root/'b')
                self.assertEqual(a.read_bytes(),b.read_bytes())

    def test_reserved_id_and_overwrite(self):
        p=self.project();p.fxid=241
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'reserved'):patch_project(p,td,allow_identity_replace=True)
            p.fxid=700
            patch_project(p,td)
            with self.assertRaises(FileExistsError):patch_project(p,td)
            patch_project(p,td,overwrite=True)

    def test_exact_boundary_and_custom_artwork(self):
        from irbq.dsp import Biquad
        from PIL import Image
        p=self.project(4,424)
        for i,slot in enumerate(p.slots):
            slot.model.sections=[Biquad(kind='Peak',f=200.+100*j+10*i,gain=.25*(j+1)) for j in range(4)]
        self.assertEqual(bank_usage(p)['code_const_bytes'],CODE_CONST_CAP)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            target,r=patch_project(p,root/'edge')
            self.assertEqual(r['code_const_bytes'],CODE_CONST_CAP)
            image=root/'card.png';Image.new('L',(128,64),255).save(image)
            p.image=str(image)
            target,_=patch_project(p,root/'image')
            self.assertTrue(target.exists())
            self.assertEqual(bank_usage(p)['code_const_bytes'],CODE_CONST_CAP)


if __name__=='__main__':unittest.main()
