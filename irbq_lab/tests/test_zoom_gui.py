import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from irbq.dsp import Model
from irbq.zoom_bank import BankProject


@unittest.skipUnless(os.name=='nt' or os.environ.get('DISPLAY'),'Desktop required')
class TestZoomGUI(unittest.TestCase):
    def test_trainer_only_and_build_close_guard(self):
        from irbq.gui import App
        with patch.dict(os.environ,{'HYBRIDIR_ZDL_ENABLED':'0'}):
            app=App();app.withdraw()
            try:
                self.assertIn('disabled',app.zoom_panel.build_button.state())
                self.assertNotIn('disabled',app.zoom_panel.patch_button.state())
                with self.assertRaisesRegex(ValueError,'disabled'):app.zoom_panel.build()
                app.zoom_panel.append(Model(44100,np.r_[.1,np.zeros(31)],[]),'TEST')
                with tempfile.TemporaryDirectory() as td, patch('irbq.zoom_panel.filedialog.askdirectory',return_value=td), patch.object(app,'run_job') as job, patch('irbq.zoom_patch.patch_project') as patcher:
                    app.zoom_panel.build(patch=True)
                    job.assert_called_once()
                    job.call_args.args[0]()
                    patcher.assert_called_once()
                    self.assertFalse(job.call_args.kwargs['cancellable'])
                    sidecar=Path(td)/(app.zoom_panel.project.filename+'.patch.json')
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
            self.assertTrue(panel.dirty)
            app.update_idletasks()
        finally:
            app.player.close();app.destroy()

if __name__=='__main__':unittest.main()
