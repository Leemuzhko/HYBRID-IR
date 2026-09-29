import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
from irbq.project import Session
from irbq.dsp import Model
from irbq.authoring import session_bytes,session_from_bytes,model_session
from irbq.zoom_bank import BankProject,Slot


def session(folder):
    path=Path(folder)/'original.wav'
    sf.write(path,np.c_[np.r_[.5,np.zeros(63)],np.r_[.25,np.zeros(63)]],48000,subtype='PCM_16')
    s=Session();s.load_audio(path);s.model=Model(44100,np.r_[.5,np.zeros(63)],[])
    return s,path.read_bytes()


class OriginalAudioTests(unittest.TestCase):
    def test_container_bytes_and_stereo_rate_survive_project(self):
        with tempfile.TemporaryDirectory() as td:
            s,raw=session(td);r=session_from_bytes(session_bytes(s))
            self.assertEqual(raw,r.source_audio)
            np.testing.assert_array_equal(s.source,r.source)
            self.assertEqual(r.source_fs,48000)
            self.assertEqual(r.model.fs,44100)

    def test_bank_deduplicates_raw_source_and_reopens_without_original_file(self):
        with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'IRBQ_SETTINGS_PATH':str(Path(td)/'settings.json')}):
            s,raw=session(td);p=BankProject(slots=[Slot('A',s.model,s),Slot('B',s.model,s)])
            path=Path(td)/'bank.hybridbank';p.save(path)
            (Path(td)/'original.wav').unlink()
            with zipfile.ZipFile(path) as z:
                self.assertEqual(len([n for n in z.namelist() if n.startswith('sources/')]),1)
                self.assertEqual(json.loads(z.read('bank.json'))['schema'],'hybrid-ir-bank/2')
            loaded=BankProject.load(path)
            self.assertEqual(loaded.slots[1].session.source_audio,raw)
            self.assertIs(loaded.slots[0].session.source_audio,loaded.slots[1].session.source_audio)

    def test_legacy_without_source_is_honest(self):
        s=model_session(Model(44100,np.r_[1.,np.zeros(31)],[]))
        r=session_from_bytes(session_bytes(s))
        self.assertIsNone(r.source_audio);self.assertIsNone(r.source)

    def test_source_mismatch_cannot_publish(self):
        with tempfile.TemporaryDirectory() as td:
            s,_=session(td);s.source[0,0]=.7
            with self.assertRaisesRegex(ValueError,'does not match'):session_bytes(s)

    def test_corrupt_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            s,_=session(td)
            with zipfile.ZipFile(io.BytesIO(session_bytes(s))) as z:files={n:z.read(n) for n in z.namelist()}
            files['original.audio']=b'not audio'
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as z:
                for name,raw in files.items():z.writestr(name,raw)
            with self.assertRaisesRegex(ValueError,'hash mismatch'):session_from_bytes(out.getvalue())

    def test_library_retained_budget_includes_original_container(self):
        from irbq.authoring import scan_library
        class SizedSource:
            def __len__(self):return 32_000_000
        s=model_session(Model(44100,np.r_[1.,np.zeros(31)],[]))
        s.source_audio=SizedSource()  # Test accounting without allocating 288 MB.
        with tempfile.TemporaryDirectory() as td,patch('irbq.authoring.library_session',return_value=s):
            for i in range(9):(Path(td)/f'{i}.irbq').touch()
            entries,errors=scan_library(td)
            self.assertEqual((len(entries),len(errors)),(8,1))
            self.assertIn('memory budget',errors[0][1])


if __name__=='__main__':unittest.main()
