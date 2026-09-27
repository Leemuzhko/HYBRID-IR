import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import numpy as np
from irbq.authoring import session_bytes, session_from_bytes, model_session, scan_library
from irbq.project import Session
from irbq.dsp import Model, preset_sections
from irbq.zoom_bank import BankProject, Slot, pack_bank
from irbq.zoom_rbj_bank import pack


def example():
    model=Model(44100,np.r_[.25,np.zeros(63)],preset_sections(4),output_gain_db=-2.)
    return Session(source=np.arange(128,dtype=float)/128,source_name='test.wav',target=np.r_[1.,np.zeros(127)],
        before_mpt=np.r_[.5,np.zeros(127)],model=model,snapshots=[model.clone()])


class AuthoringTests(unittest.TestCase):
    def test_full_session_exact_roundtrip(self):
        s=example();r=session_from_bytes(session_bytes(s))
        for key in ('source','target','before_mpt'):np.testing.assert_array_equal(getattr(s,key),getattr(r,key))
        self.assertEqual(s.model.to_dict(),r.model.to_dict());self.assertEqual(s.snapshots[0].to_dict(),r.snapshots[0].to_dict())

    def test_model_only_is_not_fake_reference(self):
        s=model_session(example().model);r=session_from_bytes(session_bytes(s))
        self.assertIsNone(r.source);self.assertIsNone(r.target);self.assertEqual(s.model.to_dict(),r.model.to_dict())

    def test_old_project_schema_loads(self):
        raw=session_bytes(example())
        with zipfile.ZipFile(io.BytesIO(raw)) as z:meta=json.loads(z.read('project.json'));payload=z.read('signals.npz')
        meta['schema']='irbq-project/1'
        self.assertIsNotNone(session_from_bytes(self.container(meta,payload)).target)

    @staticmethod
    def container(meta,payload):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:z.writestr('project.json',json.dumps(meta));z.writestr('signals.npz',payload)
        return out.getvalue()

    def test_array_declaration_rejected_before_allocation(self):
        with zipfile.ZipFile(io.BytesIO(session_bytes(example()))) as z:meta=json.loads(z.read('project.json'))
        npy=io.BytesIO();np.lib.format.write_array_header_1_0(npy,dict(descr='<f8',fortran_order=False,shape=(1000000000,)))
        npz=io.BytesIO()
        with zipfile.ZipFile(npz,'w') as z:z.writestr('target.npy',npy.getvalue())
        with self.assertRaisesRegex(ValueError,'dimensions'):session_from_bytes(self.container(meta,npz.getvalue()))

    def test_nan_signal_rejected(self):
        s=example();s.target[0]=np.nan
        with self.assertRaisesRegex(ValueError,'signal'):session_bytes(s)

    def test_signal_budget_checked_before_allocation(self):
        with self.assertRaisesRegex(ValueError,'memory budget'):session_from_bytes(session_bytes(example()),8)

    def test_invalid_card_prevents_portable_publication(self):
        with tempfile.TemporaryDirectory() as td:
            card=Path(td)/'card.png';card.write_bytes(b'not a PNG')
            project=BankProject(image=str(card),slots=[Slot('A',example().model)])
            dest=Path(td)/'invalid.hybridbank'
            with self.assertRaises(OSError):project.save(dest)
            self.assertFalse(dest.exists())

    def test_bank_survives_move_and_keeps_coefficients(self):
        with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'IRBQ_SETTINGS_PATH':str(Path(td)/'settings.json')}):
            s=example();p=BankProject(slots=[Slot('CAB',s.model.clone(),s)],patched_folder='C:/private/output')
            before=pack(p)[0];path=Path(td)/'a.hybridbank';p.save(path)
            moved=Path(td)/'moved.hybridbank';path.rename(moved);r=BankProject.load(moved)
            self.assertEqual(before,pack(r)[0]);self.assertEqual(p.slots[0].uid,r.slots[0].uid)
            np.testing.assert_array_equal(s.target,r.slots[0].session.target)
            self.assertEqual(r.patched_folder,'');self.assertTrue(Path(r.image).is_file())
            with zipfile.ZipFile(moved) as z:self.assertNotIn('private',z.read('bank.json').decode())

    def test_empty_portable_bank_saves_but_does_not_export(self):
        with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'IRBQ_SETTINGS_PATH':str(Path(td)/'settings.json')}):
            path=Path(td)/'empty.hybridbank';BankProject().save(path);r=BankProject.load(path)
            self.assertEqual(r.slots,[])
            with self.assertRaises(ValueError):pack_bank(r)

    def test_portable_bank_rejects_external_folder_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'external.hybridbank';BankProject().save(path)
            with zipfile.ZipFile(path) as z:files={name:z.read(name) for name in z.namelist()}
            metadata=json.loads(files['bank.json']);metadata['patched_folder']='C:/Sensitive/Output'
            files['bank.json']=json.dumps(metadata).encode()
            with zipfile.ZipFile(path,'w') as z:
                for name,raw in files.items():z.writestr(name,raw)
            with self.assertRaisesRegex(ValueError,'local paths'):BankProject.load(path)

    def test_invalid_role_is_reported_by_scan_not_rendered(self):
        with tempfile.TemporaryDirectory() as td:
            model=example().model;model.sections[0].control_role='unknown'
            (Path(td)/'model.json').write_text(json.dumps(model.to_dict()),encoding='utf-8')
            entries,errors=scan_library(td)
            self.assertEqual(entries,[]);self.assertEqual(len(errors),1)
            self.assertIn('role',errors[0][1])

    def test_uid_duplicates_rejected(self):
        s=example();a=Slot('A',s.model);b=Slot('B',s.model,uid=a.uid)
        with self.assertRaisesRegex(ValueError,'identity'):BankProject(slots=[a,b]).validate()

    def test_library_reads_projects_and_models_and_reports_bad_files(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);example().save(folder/'cab.irbq')
            (folder/'sub').mkdir();(folder/'sub'/'model.json').write_text(json.dumps(example().model.to_dict()),encoding='utf-8')
            (folder/'broken.irbq').write_bytes(b'bad zip')
            entries,errors=scan_library(folder)
            self.assertEqual(len(entries),2);self.assertEqual(len(errors),1)
            self.assertIsNone(entries[1].session.target)

    def test_library_scan_can_be_cancelled_before_loading(self):
        with tempfile.TemporaryDirectory() as td:
            example().save(Path(td)/'cab.irbq')
            def cancelled():raise InterruptedError('cancel')
            with self.assertRaisesRegex(InterruptedError,'cancel'):scan_library(td,cancelled)


if __name__=='__main__':unittest.main()
