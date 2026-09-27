"""GUI smoke tests. Run with a real display or xvfb-run. No sound device needed."""
import os
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

@unittest.skipUnless(os.environ.get('DISPLAY') or os.name=='nt','GUI test requires DISPLAY / Windows desktop')
class TestGUI(unittest.TestCase):
    def test_editor_training_plots(self):
        from irbq.gui import App, BQEditor, PLOTS
        from irbq.project import Session
        from irbq.dsp import Model,PrepConfig,Biquad,preset_sections
        app=App()
        errors=[]
        app.error=lambda e:errors.append(str(e))
        try:
            s=Session(source=np.r_[np.zeros(8),1.,.2,np.zeros(500)],source_fs=44100,
                      config=PrepConfig(fs=44100,minimum_phase=False))
            s.preprocess();s.model=Model(44100,s.target[:32].copy(),preset_sections(4,False,44100),'UI smoke')
            app.session=s;app.sync_prep();app.changed();app.update()
            for mode in PLOTS:
                app.plotvar.set(mode);app.redraw();app.update()
            app.session.snapshots.append(app.session.model.clone());app.refresh_snapshots()
            app.stree.selection_set('0');app.showquant.set(True);app.pure.set('1024');app.redraw();app.update()
            b=app.session.model.sections[1]
            got=[]
            editor=BQEditor(app,b,44100,got.append)
            editor.vars['f'].set('135');editor.vars['gain'].set('4');editor.apply();app.update()
            self.assertEqual(got[0].f,135.)
            before=app.session.model.clone()
            app.bqtree.selection_set('1');app.toggle_bq();self.assertFalse(app.session.model.sections[1].enabled)
            app.undo();self.assertTrue(app.session.model.sections[1].enabled)
            app.bqtree.selection_set('1');app.sync_eq_quick();app.eq_f.set('777');app.eq_gain.set('2.5');app.eq_quick_apply();app.update()
            self.assertAlmostEqual(app.session.model.sections[1].f,777.)
            app.fir_enabled.set(False);app.toggle_fir_path();self.assertFalse(app.session.model.fir_enabled)
            app.fir_enabled.set(True);app.toggle_fir_path();self.assertTrue(app.session.model.fir_enabled)
            app.draw_eq_editor();app.update()
            app.fitvars['iterations'].set('3');app.fitvars['rounds'].set('1');app.greedy.set(False)
            app.start_train()
            deadline=time.time()+25
            while app.busy and time.time()<deadline:
                app.update();time.sleep(.02)
            self.assertFalse(app.busy)
            app.redraw();app.update()
            self.assertFalse(errors,errors)
            self.assertTrue(app.session.model.training)
            app.prepare_audio()
            deadline=time.time()+15
            while app.busy and time.time()<deadline:
                app.update();time.sleep(.02)
            self.assertFalse(app.busy)
            self.assertIsNotNone(app.audio_render)
            self.assertFalse(errors,errors)
        finally:
            app.dirty=False
            app.close()

if __name__=='__main__':unittest.main(verbosity=2)
