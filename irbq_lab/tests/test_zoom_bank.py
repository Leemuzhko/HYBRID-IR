import sys
from pathlib import Path
import tempfile
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irbq.dsp import Model, Biquad
from irbq.zoom_bank import BankProject, Slot, pack_bank, validate_model, identity_conflicts, import_irbq_package


class TestZoomBank(unittest.TestCase):
    def model(self):
        return Model(44100, np.r_[1.,np.zeros(31)], [], output_gain_db=-6.)

    def test_persistence(self):
        p = BankProject(slots=[Slot('CAB1',self.model())])
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'bank.json'
            p.save(path)
            q = BankProject.load(path)
            self.assertEqual(q.slots[0].model.output_gain_db,-6.)
            self.assertEqual(pack_bank(p),pack_bank(q))

    def test_dedup_and_addressing(self):
        p = BankProject(slots=[Slot('CAB'+str(i),self.model()) for i in range(8)])
        text,r = pack_bank(p)
        self.assertEqual(r['fir_pool_samples'],32)
        self.assertEqual(r['bq_pool_sections'],2)
        self.assertEqual(r['entry_count'],9)
        self.assertEqual(r['max_fir'],32)
        self.assertIn('#define GJ_BANK_ENTRY_COUNT 9u',text)

    def test_reserved_controls_and_gain(self):
        m=self.model()
        m.sections=[Biquad(kind='Peak',gain=3.)]
        text,r=pack_bank(BankProject(slots=[Slot('CAB1',m)]))
        self.assertEqual(r['max_bq'],3)
        self.assertIn('5.011872',text)

    def test_invalid_models(self):
        for count in (9,20,31):
            with self.assertRaisesRegex(ValueError,'Compatibility envelope'):
                BankProject(slots=[Slot(f'C{i}',self.model()) for i in range(count)]).validate()
        m=self.model();m.fs=48000
        with self.assertRaises(ValueError):validate_model(m)
        m=self.model();m.fir[0]=np.nan
        with self.assertRaises(ValueError):validate_model(m)
        m=self.model();m.sections=[Biquad(kind='SOS',raw=[1.,0.,0.,1.,0.,1.1])]
        with self.assertRaises(ValueError):validate_model(m)

    def test_labels_and_ids(self):
        for label in ('OFF','too long name','строка'):
            with self.assertRaises(ValueError):
                BankProject(slots=[Slot(label,self.model())]).validate()
        with tempfile.TemporaryDirectory() as td:
            fixture=Path(__file__).resolve().parents[2]/'hybridir_sdk/dist/hybridir-folder/HYBRIDIR.ZDL'
            if not fixture.exists():
                self.skipTest('Private ZDL fixture is not bundled')
            raw=fixture.read_bytes()
            path=Path(td)/'existing.ZDL';path.write_bytes(raw)
            p=BankProject(slots=[Slot('A',self.model())],patched_folder=td)
            self.assertEqual(identity_conflicts(p),[str(path)])

    def test_trainer_export_contract(self):
        import json
        from irbq.project import Session,export_model
        m=self.model();m.fir_enabled=False
        m.sections=[Biquad(kind='SOS',raw=[.9,-.1,.02,1.,-.2,.05])]
        with tempfile.TemporaryDirectory() as td:
            export_model(td,Session(model=m,target=np.r_[1.,np.zeros(127)]))
            path=Path(td)/'model.json'
            imported=import_irbq_package(path)
            self.assertFalse(imported.fir_enabled)
            self.assertEqual(imported.output_gain_db,-6.)
            self.assertEqual(imported.sections[0].raw,m.sections[0].raw)
            d=json.loads(path.read_text(encoding='utf-8'));d['fir_gain']=2.
            path.write_text(json.dumps(d),encoding='utf-8')
            with self.assertRaises(ValueError):import_irbq_package(path)

if __name__=='__main__':unittest.main()
