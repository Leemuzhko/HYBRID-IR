"""Release gates for HIR3A, K-weighted normalization and saved preparation defaults."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from irbq.dsp import Model, PrepConfig, prepare, k_weighting_response, response_normalization_power
from irbq.zoom_bank import BankProject, Slot, SDK
from irbq.template_profile import load_package
from irbq.template_patch import bank_usage, plan_patch, patch_project

MODES=('k_weighted','k_band','k_pink','k_pink_band')

class ReleaseFeatures(unittest.TestCase):
    def test_k_filter_matches_bs1770_48k_reference(self):
        # BS.1770 reference coefficients, independently evaluated as two SOS.
        f=np.geomspace(20,20000,2048);z=np.exp(-2j*np.pi*f/48000)
        shelf=(1.53512485958697-2.69169618940638*z+1.19839281085285*z*z)/(1-1.69065929318241*z+.73248077421585*z*z)
        hp=(1-2*z+z*z)/(1-1.99004745483398*z+.99007225036621*z*z)
        np.testing.assert_allclose(k_weighting_response(f,48000),shelf*hp,rtol=1e-8,atol=1e-9)

    def test_shaped_ir_normalizes_at_44100_and_48000(self):
        h=np.exp(-np.arange(128)/11)*np.cos(.45*np.arange(128))
        for fs in (44100,48000):
            for mode in MODES:
                with self.subTest(fs=fs,mode=mode):
                    cfg=PrepConfig(fs=fs,trim_start=False,minimum_phase=False,normalization=mode,level_db=-3)
                    out,_,_=prepare(h,fs,cfg)
                    f=np.fft.rfftfreq(65536,1/fs);H=np.fft.rfft(out,65536)
                    self.assertAlmostEqual(10*np.log10(response_normalization_power(H,f,fs,mode)),-3,places=8)

    def test_empty_preview_is_valid_but_export_is_rejected_without_output(self):
        package=load_package(SDK/'templates/HIR3A.template.json')
        p=BankProject();report=bank_usage(p,package)
        self.assertEqual(report['active_slots'],0)
        self.assertFalse(report['template_fits'])
        self.assertEqual(report['const_budget'],12104)
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'effect'
            with self.assertRaises(ValueError):
                patch_project(p,out,profile_path=package.profile_path,allow_experimental=True)
            self.assertFalse(out.exists())

    def test_hir3a_multi_slot_export_roundtrip_and_budget_gate(self):
        package=load_package(SDK/'templates/HIR3A.template.json')
        self.assertEqual(hashlib.sha256(package.raw).hexdigest(),'14f605e66ea0ca24a1bd0b0873cb15b8dbaf900290ffe78f9f6cb60c99b0f9d4')
        p=BankProject(name='RELEASE TEST',filename='RELTEST',fxid=901,slots=[Slot('UNIT',Model(44100,np.r_[.25,np.zeros(63)],[]))])
        old=copy.deepcopy(p.slots[0].model.to_dict())
        with tempfile.TemporaryDirectory() as td:
            path,report=patch_project(p,Path(td),profile_path=package.profile_path,allow_experimental=True)
            meta=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
            self.assertEqual(meta['inDeviceFileName'],'RELTEST.ZDL')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),report['sha256'])
            from PIL import Image
            with Image.open(path.with_suffix('.png')) as im:self.assertEqual((im.mode,im.size),('RGBA',(128,96)))
        self.assertEqual(p.slots[0].model.to_dict(),old)
        p.slots=[Slot('C'+str(i),Model(44100,np.r_[.1+i*.01,np.zeros(63)],[])) for i in range(8)]
        self.assertEqual(plan_patch(p,package).report['active_slots'],8)
        p.slots=[Slot('LONG'+str(i),Model(44100,np.r_[.1+i*.01,np.zeros(4095)],[])) for i in range(2)]
        with self.assertRaisesRegex(ValueError,'profile|capacity|budget'):plan_patch(p,package)

@unittest.skipUnless(os.name=='nt' or os.environ.get('DISPLAY'),'Desktop required')
class DefaultsGUI(unittest.TestCase):
    def test_defaults_survive_restart_and_all_k_modes_are_selectable(self):
        from irbq.gui import App,NORM_NAMES
        from irbq.i18n import set_language
        for mode in MODES:self.assertIn(mode,NORM_NAMES.values())
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ,{'IRBQ_SETTINGS_PATH':str(Path(td)/'settings.json')}):
            app=App();app.withdraw()
            try:
                for mode in MODES:
                    cfg=PrepConfig(normalization=mode,level_db=-3.5,minimum_phase=False,trim_start=False)
                    app._sync_prep_config(cfg);app.save_prep_defaults()
                    self.assertEqual(app.prefs.prep_defaults['normalization'],mode)
                app._sync_prep_config(PrepConfig());app.load_prep_defaults()
                self.assertEqual(app.read_prep().normalization,'k_pink_band')
            finally:app.player.close();app.destroy()
            restarted=App();restarted.withdraw()
            try:
                self.assertEqual(restarted.read_prep().normalization,'k_pink_band')
                self.assertEqual(restarted.read_prep().level_db,-3.5)
                p=restarted.zoom_panel
                self.assertEqual(Path(p.template_path).name,'HIR3A.template.json')
                self.assertEqual(p.estimate()['active_slots'],0)
            finally:restarted.player.close();restarted.destroy();set_language('en')

    def test_default_save_failure_is_not_reported_as_success(self):
        from irbq.gui import App
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ,{'IRBQ_SETTINGS_PATH':str(Path(td)/'settings.json')}):
            app=App();app.withdraw()
            try:
                app.status.set('unchanged')
                old=copy.deepcopy(app.prefs.prep_defaults)
                with patch('irbq.preferences.save_preferences',side_effect=OSError('read-only')),patch.object(app,'error') as error:
                    app.save_prep_defaults();error.assert_called_once()
                self.assertEqual(app.prefs.prep_defaults,old)
                self.assertEqual(app.status.get(),'unchanged')
            finally:app.player.close();app.destroy()

if __name__=='__main__':unittest.main()
