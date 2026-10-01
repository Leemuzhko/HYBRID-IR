import copy
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from irbq.dsp import Model
from irbq.zoom_bank import BankProject,Slot


@unittest.skipUnless((os.name=='nt' or sys.platform=='darwin') or os.environ.get('DISPLAY'),'Desktop required')
class TestZoomGUI(unittest.TestCase):
    def test_default_passport_is_hardware_checked_v3(self):
        from irbq.gui import App
        from irbq.template_profile import load_package
        app=App();app.withdraw()
        try:
            panel=app.zoom_panel
            self.assertEqual(Path(panel.template_path).name,'HIR3A.template.json')
            self.assertIn('HIR3A.template.json',panel.template_menu.entrycget(0,'label'))
            package=load_package(panel.template_path)
            self.assertEqual(package.profile['sha256'],'14f605e66ea0ca24a1bd0b0873cb15b8dbaf900290ffe78f9f6cb60c99b0f9d4')
            self.assertEqual(package.profile['acceptance']['status'],'historical-pass')
            panel.append(Model(44100,np.r_[.1,np.zeros(31)],[]),'TEST')
            self.assertEqual(panel.usage(panel.project)['const_budget'],12104)
            panel.variables['patched_folder'].set(self.profile.name)
            with patch.object(app,'run_job') as job, patch('irbq.template_patch.publish_plan') as publish:
                panel.build(patch=True)
                plan=job.call_args.args[0]()
                callback=job.call_args.args[1]
                callback(plan)
                job.call_args.args[0]()
                publish.assert_called_once()
                self.assertEqual(publish.call_args.args[1].profile['sha256'],package.profile['sha256'])
        finally:app.player.close();app.destroy()

    def setUp(self):
        self.profile=tempfile.TemporaryDirectory()
        self.profile_patch=patch.dict(os.environ,{'IRBQ_SETTINGS_PATH':str(Path(self.profile.name)/'settings.json')})
        self.profile_patch.start()
        self.diagnostic_confirm=patch('irbq.zoom_panel.messagebox.askyesno',return_value=True)
        self.diagnostic_confirm.start()

    def tearDown(self):
        self.diagnostic_confirm.stop();self.profile_patch.stop();self.profile.cleanup()

    def test_legacy_diagnostic_warning_can_cancel_before_export(self):
        from irbq.gui import App
        app=App();app.withdraw()
        try:
            panel=app.zoom_panel;panel.use_legacy_template();panel.append(Model(44100,np.r_[.1,np.zeros(31)],[]),'TEST')
            panel.variables['patched_folder'].set(self.profile.name)
            with patch('irbq.zoom_panel.messagebox.askyesno',return_value=False) as confirm,patch.object(app,'run_job') as job:
                panel.build(patch=True)
                self.assertIn('known pedal insertion failure',confirm.call_args.args[1])
                job.assert_not_called()
        finally:app.player.close();app.destroy()

    def test_trainer_only_and_build_close_guard(self):
        from irbq.gui import App
        with patch.dict(os.environ,{'HYBRIDIR_ZDL_ENABLED':'0'}):
            app=App();app.withdraw()
            try:
                self.assertIn('disabled',app.zoom_panel.build_button.state())
                self.assertNotIn('disabled',app.zoom_panel.patch_button.state())
                with self.assertRaisesRegex(ValueError,'disabled'):app.zoom_panel.build()
                app.zoom_panel.use_legacy_template()
                app.zoom_panel.append(Model(44100,np.r_[.1,np.zeros(31)],[]),'TEST')
                with tempfile.TemporaryDirectory() as td, patch('irbq.zoom_panel.filedialog.askdirectory',return_value=td), patch.object(app,'run_job') as job, patch('irbq.zoom_variable_patch.patch_project') as patcher:
                    app.zoom_panel.build(patch=True)
                    job.assert_called_once()
                    job.call_args.args[0]()
                    patcher.assert_called_once()
                    self.assertFalse(job.call_args.kwargs['cancellable'])
                    sidecar=Path(td)/app.zoom_panel.project.filename/(app.zoom_panel.project.filename+'.patch.json')
                    sidecar.parent.mkdir()
                    sidecar.write_text('keep',encoding='utf-8')
                    job.reset_mock()
                    with patch('irbq.zoom_panel.messagebox.askyesno',return_value=False) as confirm:
                        app.zoom_panel.build(patch=True)
                        confirm.assert_called_once()
                        self.assertIn(str(sidecar),confirm.call_args.args[1])
                        job.assert_not_called()
                    with patch('irbq.zoom_panel.messagebox.askyesno',return_value=True):
                        app.zoom_panel.build(patch=True)
                        job.call_args.args[0]()
                        self.assertTrue(patcher.call_args.args[2])
                app.busy=True;app.job_cancellable=False
                with patch('irbq.gui.messagebox.showinfo') as notice, patch.object(app,'destroy') as destroy:
                    app.close();notice.assert_called_once();destroy.assert_not_called()
                app.cancel_event.clear();app.cancel()
                self.assertFalse(app.cancel_event.is_set())
                app.update_idletasks()
            finally:
                app.busy=False;app.player.close();app.destroy()

    def test_bank_tab_roundtrip_and_slot_actions(self):
        from irbq.gui import App
        app=App();app.withdraw()
        try:
            panel=app.zoom_panel
            def labels(widget):
                found=[]
                if widget.winfo_class()=='TLabel':found.append(str(widget.cget('text')))
                for child in widget.winfo_children():found.extend(labels(child))
                return found
            self.assertIn('Zoom Effect Manager custom folder:',labels(panel))
            # Preparation must be deferred; worker must not touch Tk widgets.
            with patch('irbq.zoom_panel.filedialog.askopenfilename',return_value='test.wav'), \
                 patch('irbq.zoom_panel.simpledialog.askinteger',return_value=32), \
                 patch.object(app,'run_job') as job, \
                 patch('irbq.zoom_panel.Session.load_audio') as load:
                panel.import_wav()
                load.assert_not_called()
                self.assertEqual(job.call_count,1)
            app.session.model=Model(44100,np.r_[.2,np.zeros(31)],[],output_gain_db=-3.)
            panel.append(app.session.model,'A')
            panel.append(app.session.model,'B')
            usage=panel.update_budget()
            self.assertEqual(usage['active_slots'],2)
            self.assertGreater(float(panel.capacity_bar['value']),0)
            self.assertIn('244',panel.capacity_text.get())
            panel.tree.selection_set('0');panel.move(1)
            self.assertEqual([s.label for s in panel.project.slots],['B','A'])
            with patch('irbq.zoom_panel.simpledialog.askstring',return_value='CAB2'):panel.rename()
            self.assertEqual(panel.project.slots[1].label,'CAB2')
            report=panel.estimate()
            self.assertEqual(report['fir_pool_samples'],32)
            with tempfile.TemporaryDirectory() as td:
                path=Path(td)/'bank.zoombank.json'
                with patch('irbq.zoom_panel.filedialog.asksaveasfilename',return_value=str(path)):panel.save()
                with patch('irbq.zoom_panel.filedialog.askopenfilename',return_value=str(path)):panel.open()
                self.assertEqual(panel.project.slots[0].model.output_gain_db,-3.)
            self.assertIn('Zoom ZDL',[app.tabs.tab(t,'text') for t in app.tabs.tabs()])
            panel.variables['name'].set('TEST IR')
            self.assertTrue(app.apply_preferences('en','dark'))
            panel=app.zoom_panel
            self.assertEqual(panel.variables['name'].get(),'TEST IR')
            self.assertEqual([s.label for s in panel.project.slots],['B','CAB2'])
            self.assertEqual(panel.update_budget()['active_slots'],2)
            self.assertTrue(panel.dirty)
            previous_image=panel.variables['image'].get()
            panel.variables['image'].set('missing.png')
            self.assertIsNone(panel.update_budget())
            self.assertEqual(float(panel.capacity_bar['value']),0)
            self.assertIn('Capacity unavailable',panel.capacity_text.get())
            panel.variables['image'].set(previous_image)
            self.assertIsNotNone(panel.update_budget())
            app.update_idletasks()
        finally:
            app.player.close();app.destroy()

    def test_export_uses_custom_folder_and_confirms_completed_save(self):
        from irbq.gui import App
        app=App();app.withdraw()
        try:
            panel=app.zoom_panel
            panel.append(Model(44100,np.r_[.1,np.zeros(31)],[]),'TEST')
            with tempfile.TemporaryDirectory() as td:
                panel.variables['patched_folder'].set(td)
                for patch_mode,builder_name in ((False,'irbq.zoom_panel.build_project'),
                                                 (True,'irbq.zoom_variable_patch.patch_project')):
                    panel.use_legacy_template()
                    with self.subTest(patch=patch_mode), \
                         patch('irbq.zoom_panel.filedialog.askdirectory') as chooser, \
                         patch('irbq.zoom_panel.messagebox.showinfo') as notice, \
                         patch.object(app,'run_job') as job, patch(builder_name) as builder:
                        path=Path(td)/'TEST.zdl'
                        builder.return_value=(path,{'sha256':'test-hash'})
                        panel.build(patch=patch_mode)
                        chooser.assert_not_called();notice.assert_not_called()
                        job.assert_called_once()
                        result=job.call_args.args[0]()
                        self.assertEqual(builder.call_args.args[1],td)
                        job.call_args.args[1](result)
                        notice.assert_called_once()
                        self.assertIn(str(path.resolve()),notice.call_args.args[1])
                        self.assertIn('successfully',notice.call_args.args[1])
        finally:app.player.close();app.destroy()

    def test_template_selection_cancel_and_non_destructive_conversion(self):
        from irbq.gui import App
        from tests.test_template_packages import passport
        from irbq.dsp import Biquad
        app=App();app.withdraw()
        try:
            panel=app.zoom_panel
            panel.append(Model(44100,np.r_[.25,np.zeros(63)],[]),'TEST')
            panel.project.slots[0].model.sections=[Biquad(kind='Peak',f=600,gain=3,control_role='reso')]
            before=panel.project.slots[0].model.to_dict()
            with tempfile.TemporaryDirectory() as td:
                path=passport(td)
                with patch('irbq.zoom_panel.filedialog.askopenfilename',return_value=str(path)):panel.choose_template()
                self.assertEqual(panel.template_path,str(path.resolve()))
                with patch('irbq.zoom_panel.simpledialog.askinteger',return_value=None):panel.choose_preparation('bake')
                self.assertEqual(panel.export_mode,'preserve')
                with patch('irbq.zoom_panel.simpledialog.askinteger',return_value=512):panel.choose_preparation('bake')
                self.assertTrue(panel.update_budget()['template_fits'])
                (Path(td)/'out').mkdir()
                panel.variables['patched_folder'].set(str(Path(td)/'out'))
                with patch('irbq.zoom_panel.messagebox.askyesno',return_value=False),patch.object(app,'run_job') as job:
                    panel.build(patch=True)
                    prepare_job=job.call_args.args
                    prepare_job[1](prepare_job[0]())
                    self.assertEqual(job.call_count,1)  # preparation only, no publication
                self.assertEqual(panel.project.slots[0].model.to_dict(),before)
                state=panel.capture();panel.use_legacy_template();panel.restore(state)
                self.assertEqual(panel.export_mode,'bake');self.assertEqual(panel.export_taps,512)
                self.assertEqual(panel.template_path,str(path.resolve()))
                with patch('irbq.zoom_panel.messagebox.askyesno',return_value=True),patch.object(app,'run_job') as job:
                    panel.build(patch=True)
                    prepare_job=job.call_args.args
                    prepare_job[1](prepare_job[0]())
                    self.assertEqual(job.call_count,2)
                    result=job.call_args.args[0]()
                    self.assertTrue(result[0].exists())
                    self.assertEqual(result[1]['preparation']['mode'],'bake')
                self.assertEqual(panel.project.slots[0].model.to_dict(),before)
        finally:app.player.close();app.destroy()

    def test_role_migration_confirmation_and_cancel_are_inert(self):
        from irbq.gui import App
        from irbq.dsp import preset_sections
        app=App();app.withdraw()
        try:
            panel=app.zoom_panel
            model=Model(44100,np.r_[.5,np.zeros(127)],preset_sections(8))
            panel.append(model,'NEW')
            self.assertEqual(int(panel.tree.item('0','values')[2]),9)
            self.assertFalse(model.sections[-1].locked)
            legacy=model.clone()
            for b in legacy.sections:b.control_role=''
            before=legacy.to_dict()
            with patch('irbq.zoom_panel.messagebox.askyesnocancel',return_value=None):panel.append(legacy,'CANCEL')
            self.assertEqual(len(panel.project.slots),1)
            with patch('irbq.zoom_panel.messagebox.askyesnocancel',return_value=True):panel.append(legacy,'OWNED')
            self.assertEqual(int(panel.tree.item('1','values')[2]),9)
            with patch('irbq.zoom_panel.messagebox.askyesnocancel',return_value=False):panel.append(legacy,'GEN')
            self.assertEqual(int(panel.tree.item('2','values')[2]),10)
            self.assertEqual(legacy.to_dict(),before)
            with tempfile.TemporaryDirectory() as td:
                p=BankProject(slots=[Slot('OLD',legacy)])
                path=Path(td)/'old.zoombank.json';p.save(path)
                previous=panel.project
                with patch('irbq.zoom_panel.messagebox.askyesno',return_value=True), \
                     patch('irbq.zoom_panel.messagebox.askyesnocancel',return_value=None), \
                     patch('irbq.zoom_panel.filedialog.askopenfilename',return_value=str(path)):
                    panel.open()
                self.assertIs(panel.project,previous)
        finally:app.update_idletasks();app.player.close();app.destroy()


if __name__=='__main__':unittest.main()
