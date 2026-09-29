import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from irbq.dsp import Model,Biquad
from irbq.zoom_bank import BankProject,Slot
from irbq.zoom_patch import load_template as fixed_template,patch_project as fixed_patch
from irbq.zoom_variable_patch import load_template as variable_template,patch_project as variable_patch
from irbq.template_profile import make_profile,load_package,validate_profile,TemplatePackage,sha
from irbq.template_patch import plan_patch,patch_project,bank_usage
from irbq.bank_prepare import TargetModel,prepare_bank,ConversionRequired


def project():
    return BankProject(name='PROFILE TEST',filename='PROFTST',fxid=767,slots=[
        Slot('CAB',Model(44100,np.r_[.25,np.zeros(63)],[Biquad(kind='Peak',f=600,gain=3)]))])


def passport(folder,variable=False):
    raw=variable_template() if variable else fixed_template()[1]
    path=Path(folder)/'kernel.zdl';path.write_bytes(raw)
    profile=make_profile(raw,path.name,backend='hvb4-tail/1' if variable else 'irb2-fixed/1',
                         code_const_cap=28904 if variable else 30872,provenance='Synthetic test fixture')
    companion=path.with_suffix('.template.json');companion.write_text(json.dumps(profile),encoding='utf-8')
    return companion


class PreparationTests(unittest.TestCase):
    def test_preview_never_preprocesses_audio_and_is_conservative(self):
        from irbq.bank_prepare import preview_bank
        p=project();p.slots.append(copy.deepcopy(p.slots[0]));p.slots[1].uid='a'*32
        with patch('irbq.bank_prepare.prepare',side_effect=AssertionError('No preprocessing')),patch.object(Model,'render',side_effect=AssertionError('No render')):
            preview=preview_bank(p,TargetModel(),mode='bake',taps=512)
        self.assertIsNone(preview.slots[0].session)
        with tempfile.TemporaryDirectory() as td:
            package=load_package(passport(td,True))
            actual,_=prepare_bank(p,mode='bake',taps=512)
            self.assertGreaterEqual(bank_usage(preview,package)['const_bytes'],bank_usage(actual,package)['const_bytes'])

    def test_long_original_metrics_use_exact_fft_bins(self):
        from irbq.bank_prepare import conversion_metrics
        source=Model(44100,np.r_[.5,np.zeros(16383)],[])
        converted=Model(44100,np.r_[.5,np.zeros(511)],[])
        with patch.object(source,'response',side_effect=AssertionError('No long polynomial')):
            rows,grid=conversion_metrics(source,converted)
        self.assertIn('FFT bins',grid['method'])
        self.assertGreaterEqual(grid['fft_size'],len(source.fir))
        self.assertTrue(grid['bins'])
        self.assertLess(max(r['mag_max_db'] for r in rows),1e-10)

    def test_disabled_long_fir_is_ignored_by_conversion_metrics(self):
        from irbq.bank_prepare import conversion_metrics
        source=Model(44100,np.r_[.25,np.zeros(16383)],[],fir_enabled=False)
        converted=Model(44100,np.r_[1.,np.zeros(511)],[])
        rows,grid=conversion_metrics(source,converted)
        self.assertEqual(grid['method'],'direct frequency evaluation')
        self.assertLess(max(r['mag_max_db'] for r in rows),.001)

    def test_export_snapshot_borrows_only_readonly_source_and_drops_unused_arrays(self):
        from irbq.bank_prepare import export_snapshot
        from irbq.project import Session
        p=project()
        source=np.zeros(1_000_000)
        p.slots[0].session=Session(source=source,target=source,before_mpt=source,source_audio=b'container')
        for i in range(7):
            p.slots.append(Slot('C'+str(i),p.slots[0].model.clone(),p.slots[0].session))
        snap=export_snapshot(p,include_source=True)
        for slot in snap.slots:
            self.assertTrue(np.shares_memory(source,slot.session.source))
            self.assertFalse(slot.session.source.flags.writeable)
            self.assertIsNone(slot.session.target);self.assertIsNone(slot.session.before_mpt)
            self.assertIsNone(slot.session.source_audio)
        self.assertTrue(source.flags.writeable)
        prepared,_=prepare_bank(snap)
        self.assertTrue(all(slot.session is None for slot in prepared.slots))
        prepared.slots[0].model.fir[0]=.7
        self.assertEqual(p.slots[0].model.fir[0],.25)

    def test_fir_only_gets_default_controls_without_mutating_bank(self):
        from irbq.zoom_rbj_bank import pack,validate,controls
        p=project();p.slots[0].model.sections=[]
        before=p.slots[0].model.to_dict()
        prepared,r=prepare_bank(p)
        reso,pres,correction=controls(prepared.slots[0].model)
        self.assertEqual((reso.gain,pres.gain,len(correction)),(0,0,0))
        self.assertEqual(validate(pack(prepared)[0])['max_bq'],2)
        self.assertEqual(p.slots[0].model.to_dict(),before)

    def test_bake_keeps_nominal_reso_and_gain_once(self):
        p=project();m=p.slots[0].model;m.sections[0].control_role='reso';m.output_gain_db=-3
        before=m.to_dict()
        with self.assertRaises(ConversionRequired):prepare_bank(p,TargetModel(supports_bq=False))
        converted,r=prepare_bank(p,TargetModel(supports_bq=False),mode='bake',taps=2048)
        np.testing.assert_array_equal(converted.slots[0].model.fir,m.render(length=2048,quantized=True))
        self.assertEqual(converted.slots[0].model.sections,[])
        self.assertEqual(converted.slots[0].model.output_gain_db,0)
        self.assertEqual(before,m.to_dict())
        self.assertTrue(r['slots'][0]['metrics'])
        self.assertLess(max(x['mag_max_db'] for x in r['slots'][0]['metrics']),.03)

    def test_no_source_no_implicit_retraining_or_truncation(self):
        p=project()
        with self.assertRaises(ConversionRequired):prepare_bank(p,mode='original',taps=128)
        with self.assertRaises(ConversionRequired):prepare_bank(p,TargetModel(max_fir=32))
        with self.assertRaises(ValueError):prepare_bank(p,mode='bake',taps=31)
        with self.assertRaises(ValueError):prepare_bank(p,mode='bake',taps=8192)
        p.slots[0].model.sections[0].control_role='unknown'
        with self.assertRaisesRegex(ValueError,'role'):prepare_bank(p,mode='bake',taps=128)

    def test_original_uses_full_source_and_recipe_not_fitted_model(self):
        from irbq.project import Session
        from irbq.dsp import PrepConfig
        p=project();s=Session(source=np.r_[.5,np.zeros(127)],model=p.slots[0].model,
            config=PrepConfig(trim_start=False,minimum_phase=False,normalization='none'))
        p.slots[0].session=s
        out,_=prepare_bank(p,mode='original',taps=64)
        np.testing.assert_allclose(out.slots[0].model.fir,np.r_[.5,np.zeros(63)])
        self.assertIsNone(s.target)


class TemplateTests(unittest.TestCase):
    def test_both_known_backends_match_legacy_bytes_without_compiler(self):
        p=project();before=p.slots[0].model.to_dict()
        with tempfile.TemporaryDirectory() as td,patch('subprocess.run',side_effect=AssertionError('No compiler')):
            root=Path(td)
            for variable,legacy in ((False,fixed_patch),(True,variable_patch)):
                profile=passport(root,variable);package=load_package(profile)
                plan=plan_patch(p,package)
                old,_=legacy(p,root/('v' if variable else 'f'))
                self.assertEqual(old.read_bytes(),plan.raw)
                self.assertEqual(bank_usage(p,package)['code_const_bytes'],plan.report['code_const_bytes'])
                self.assertFalse(plan.report['hardware_validated'])
        self.assertEqual(before,p.slots[0].model.to_dict())

    def test_fixed_export_requires_consent_and_preserves_manager_format(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);profile=passport(root);out=root/'export'
            with self.assertRaisesRegex(ValueError,'confirmation'):patch_project(project(),out,profile_path=profile)
            self.assertFalse(out.exists())
            path,report=patch_project(project(),out,profile_path=profile,allow_experimental=True)
            meta=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
            self.assertEqual(meta['inDeviceFileName'],'PROFTST.ZDL')
            from PIL import Image
            with Image.open(path.with_suffix('.png')) as im:self.assertEqual((im.mode,im.size),('RGBA',(128,96)))
            self.assertEqual(sha(path.read_bytes()),report['sha256'])
            with self.assertRaises(FileExistsError):patch_project(project(),out,profile_path=profile,allow_experimental=True)

    def test_known_failed_template_cannot_be_exported(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);profile=passport(root,True);out=root/'export'
            with self.assertRaisesRegex(ValueError,'Known failed'):patch_project(project(),out,profile_path=profile,allow_experimental=True)
            self.assertFalse(out.exists())

    def test_profile_hash_regions_codec_and_path_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);path=passport(root);base=json.loads(path.read_text())
            cases=[dict(base,sha256='0'*64),dict(base,backend='exec-python'),dict(base,codec='unknown'),
                   dict(base,binary='../kernel.zdl'),dict(base,script='bad'),
                   dict(base,bindings=dict(base['bindings'],name=[100,12]))]
            for bad in cases:
                path.write_text(json.dumps(bad),encoding='utf-8')
                with self.subTest(bad=bad),self.assertRaises(ValueError):load_package(path)
            path.write_text('{"schema":1,"schema":2}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Duplicate'):load_package(path)

    def test_layout_specific_size_cap_and_role_compatibility(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);path=passport(root);p=project();package=load_package(path)
            p.slots[0].model.sections[0].control_role='reso'
            with self.assertRaises(ConversionRequired):plan_patch(p,package)
            plan=plan_patch(p,package,mode='bake',taps=512)
            self.assertEqual(plan.report['preparation']['mode'],'bake')
            d=json.loads(path.read_text());d['limits']['code_const_bytes']=100
            path.write_text(json.dumps(d),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'loading profile'):plan_patch(project(),load_package(path))

    def test_two_distinct_hvb4_layouts_need_no_patcher_edit(self):
        from irbq.zoom_variable_repack import repack_roles
        from irbq.zoom_rbj_bank import pack
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);profile=passport(root,True);package=load_package(profile)
            p=project();p.slots[0].model.fir=np.r_[.5,np.zeros(1023)]
            bank,_=pack(p)
            other,_=repack_roles(package.raw,bank,expected_sha256=sha(package.raw))
            d=make_profile(other,'other.zdl',backend='hvb4-tail/1',code_const_cap=28904,provenance='Synthetic host-only resized fixture')
            second=TemplatePackage(d,other,root/'other.template.json',root/'other.zdl')
            self.assertNotEqual(package.profile['sections']['.const'],d['sections']['.const'])
            self.assertEqual(plan_patch(project(),package).raw,plan_patch(project(),second).raw)

    def test_confirmed_plan_does_not_reload_changed_template(self):
        from irbq.template_patch import publish_plan
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);path=passport(root);package=load_package(path)
            plan=plan_patch(project(),package)
            package.binary_path.write_bytes(b'changed after confirmation')
            exported,_=publish_plan(plan,package,root/'out',allow_experimental=True)
            self.assertEqual(exported.read_bytes(),plan.raw)

    def test_historical_reference_is_loaded_with_its_own_budget(self):
        from irbq.zoom_bank import SDK
        package=load_package(SDK/'templates/HVB4REF.template.json')
        self.assertEqual(sha(package.raw),'a60e2b45ed00159ca034a1302b4d359319c06f1b80480dcb0f8e55e3db2bec54')
        p=project();usage=bank_usage(p,package)
        self.assertEqual(usage['const_budget'],6184)
        self.assertEqual(plan_patch(p,package).report['code_const_bytes'],usage['code_const_bytes'])


if __name__=='__main__':unittest.main()
