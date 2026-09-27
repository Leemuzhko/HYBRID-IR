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
            sidecar=Path(td)/'PATCHED'/'PATCHED.patch.json'
            sidecar.parent.mkdir()
            sidecar.write_bytes(b'keep me')
            with self.assertRaises(FileExistsError):patch_project(self.project(),td)
            self.assertEqual(sidecar.read_bytes(),b'keep me')
            self.assertFalse((sidecar.parent/'PATCHED.zdl').exists())
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

    def test_manager_package_and_overwrite(self):
        from PIL import Image
        p=self.project()
        with tempfile.TemporaryDirectory() as td:
            target,report=patch_project(p,td)
            self.assertEqual(target,Path(td)/'PATCHED'/'PATCHED.zdl')
            folder=target.parent
            self.assertEqual({f.name for f in folder.iterdir()},
                             {'PATCHED.zdl','PATCHED.json','PATCHED.png','PATCHED.patch.json'})
            metadata=json.loads((folder/'PATCHED.json').read_text(encoding='utf-8'))
            self.assertEqual(metadata['name'],p.name)
            self.assertEqual(metadata['inDeviceFileName'],'PATCHED.ZDL')
            self.assertEqual(metadata['iconFile'],'PATCHED.png')
            self.assertIn('CAB1, CAB2',metadata['descriptionEng'])
            self.assertIn('Слоты IR',metadata['descriptionRus'])
            self.assertNotIn('dependencies',metadata)
            with Image.open(folder/metadata['iconFile']) as actual, Image.open(p.image) as source:
                self.assertEqual(actual.size,(128,96))
                self.assertEqual(actual.mode,'RGBA')
                expected=source.convert('L').point(lambda v: 255 if v >= 128 else 0).resize((128,96),Image.Resampling.NEAREST)
                self.assertEqual(actual.convert('L').tobytes(),expected.tobytes())
                self.assertEqual(set(actual.getdata()),{(0,0,0,255),(255,255,255,0)})
            (folder/'user-notes.txt').write_text('keep')
            p.name='NEW NAME'
            patch_project(p,td,overwrite=True)
            self.assertEqual(json.loads((folder/'PATCHED.json').read_text())['name'],p.name)
            self.assertEqual((folder/'user-notes.txt').read_text(),'keep')

    def test_metadata_collision_and_legacy_flat_export(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/'PATCHED';folder.mkdir()
            metadata=folder/'PATCHED.json';metadata.write_text('keep')
            with self.assertRaises(FileExistsError):patch_project(self.project(),td)
            self.assertEqual(metadata.read_text(),'keep')
            self.assertFalse((folder/'PATCHED.zdl').exists())
            legacy=Path(td)/'PATCHED.zdl';legacy.write_bytes(b'old')
            with self.assertRaisesRegex(ValueError,'previous flat ZDL'):
                patch_project(self.project(),td,overwrite=True)
            self.assertEqual(legacy.read_bytes(),b'old')

    def test_package_write_failure_restores_existing_files(self):
        import irbq.zoom_export as exporter
        with tempfile.TemporaryDirectory() as td:
            target,_=patch_project(self.project(),td)
            before={f:f.read_bytes() for f in target.parent.iterdir()}
            replace=exporter.os.replace
            def fail_image(source,destination):
                if Path(source).name=='image':raise OSError('test disk failure')
                return replace(source,destination)
            with patch.object(exporter.os,'replace',side_effect=fail_image):
                with self.assertRaisesRegex(OSError,'test disk failure'):
                    patch_project(self.project(),td,overwrite=True)
            self.assertEqual({f:f.read_bytes() for f in target.parent.iterdir()},before)

    def test_failed_first_export_leaves_no_effect(self):
        import irbq.zoom_export as exporter
        with tempfile.TemporaryDirectory() as td:
            replace=exporter.os.replace
            def fail_zdl(source,destination):
                if Path(source).name=='zdl':raise OSError('test disk failure')
                return replace(source,destination)
            with patch.object(exporter.os,'replace',side_effect=fail_zdl):
                with self.assertRaisesRegex(OSError,'test disk failure'):
                    patch_project(self.project(),td)
            self.assertEqual(list(Path(td).iterdir()),[])

    @unittest.skipUnless(os.name=='nt','Windows junction semantics')
    def test_junction_outputs_rejected_without_external_writes(self):
        import _winapi
        for position in ('package','root','ancestor'):
            with self.subTest(position=position), tempfile.TemporaryDirectory() as td:
                root=Path(td);outside=root/'outside';outside.mkdir()
                marker=outside/'keep.txt';marker.write_bytes(b'unchanged')
                output=root/'output'
                if position=='root':
                    link=output
                elif position=='ancestor':
                    link=root/'link';output=link/'exports'
                else:
                    output.mkdir();link=output/'PATCHED'
                _winapi.CreateJunction(str(outside),str(link))
                try:
                    self.assertTrue(link.is_junction())
                    with self.assertRaisesRegex(ValueError,'folder'):
                        patch_project(self.project(),output,overwrite=True)
                    self.assertEqual([p.name for p in outside.iterdir()],['keep.txt'])
                    self.assertEqual(marker.read_bytes(),b'unchanged')
                finally:
                    link.rmdir()  # Removes only the junction, not the target directory.

    def test_failed_rollback_keeps_recovery_data(self):
        import irbq.zoom_export as exporter
        with tempfile.TemporaryDirectory() as td:
            target,_=patch_project(self.project(),td)
            original=(target.parent/'PATCHED.json').read_bytes()
            replace=exporter.os.replace
            def fail_restore(source,destination):
                if Path(source).name in ('image','metadata.old'):
                    raise OSError('test disk failure')
                return replace(source,destination)
            with patch.object(exporter.os,'replace',side_effect=fail_restore):
                with self.assertRaisesRegex(OSError,'recovery files retained'):
                    patch_project(self.project(),td,overwrite=True)
            recovery=list(Path(td).glob('.hybridir-package-*'))
            self.assertEqual(len(recovery),1)
            self.assertEqual((recovery[0]/'metadata.old').read_bytes(),original)
            self.assertTrue(target.exists())

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
