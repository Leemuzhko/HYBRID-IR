import copy
import os
import sys
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import numpy as np
from irbq.authoring import LibraryEntry, model_session
from irbq.dsp import Model


@unittest.skipUnless((os.name=='nt' or sys.platform=='darwin') or os.environ.get('DISPLAY'),'Desktop required')
class LibraryGUI(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.settings=patch.dict(os.environ,{'IRBQ_SETTINGS_PATH':str(Path(self.temp.name)/'settings.json')})
        self.settings.start()
        from irbq.gui import App
        self.app=App();self.app.update();self.panel=self.app.zoom_panel;self.library=self.app.library_panel
        self.library.loaded_folder=self.library.folder.get()
        self.model=Model(44100,np.r_[.1,np.zeros(63)],[])
        self.errors=[];self.app.error=lambda e:self.errors.append(str(e))

    def tearDown(self):
        self.app.player.close();self.app.destroy();self.settings.stop();self.temp.cleanup()

    def test_filters_and_batch_add_clone(self):
        self.library.entries=[LibraryEntry(Path('CabA.irbq'),model_session(self.model)),LibraryEntry(Path('CabB.irbq'),model_session(Model(44100,np.ones(128)*.01,[])))]
        self.library.filter();self.assertEqual(len(self.library.tree.get_children()),2)
        self.library.taps.set('64');self.assertEqual(self.library.tree.get_children(),('0',))
        self.library.taps.set('');self.library.query.set('cabb');self.assertEqual(self.library.tree.get_children(),('1',))
        self.library.query.set('');self.library.tree.selection_set(('0','1'));self.library.add_selected()
        self.assertEqual(len(self.panel.project.slots),2)
        self.panel.project.slots[0].model.fir[0]=5;self.assertEqual(self.model.fir[0],.1)
        self.assertTrue(all(len(s.label)<=5 for s in self.panel.project.slots))

    def test_batch_cancel_and_overflow_are_inert(self):
        self.library.entries=[LibraryEntry(Path('A.irbq'),model_session(self.model)),LibraryEntry(Path('B.irbq'),model_session(self.model))]
        self.library.filter();self.library.tree.selection_set(('0','1'))
        with patch.object(self.panel,'prepare_roles',side_effect=[self.model.clone(),None]):self.library.add_selected()
        self.assertEqual(self.panel.project.slots,[])
        for n in range(7):self.panel.append(self.model,f'C{n}')
        with self.assertRaises(ValueError):self.library.add_selected()
        self.assertEqual(len(self.panel.project.slots),7)

    def test_reserved_library_name_and_deleted_edit_target(self):
        self.library.entries=[LibraryEntry(Path('OFF.irbq'),model_session(self.model))]
        self.library.filter();self.library.tree.selection_set('0');self.library.add_selected()
        self.assertNotEqual(self.panel.project.slots[0].label,'OFF');self.panel.project.validate()
        self.panel.tree.selection_set('0');self.panel.edit_slot()
        self.app.session.model.output_gain_db=-3;self.app.changed()
        self.panel.tree.selection_set('0')
        with patch('irbq.zoom_panel.messagebox.askyesno',return_value=True):self.panel.remove()
        with self.assertRaises(ValueError):self.panel.update_slot()
        self.assertTrue(self.app.dirty);self.assertEqual(self.panel.project.slots,[])

    def test_empty_bank_save_open_and_library_edit_path(self):
        path=Path(self.temp.name)/'empty.hybridbank'
        with patch('irbq.zoom_panel.filedialog.asksaveasfilename',return_value=str(path)):self.assertTrue(self.panel.save())
        self.panel.open(path);self.assertEqual(self.panel.project.slots,[])
        session=model_session(self.model);project=Path(self.temp.name)/'cab.irbq';session.save(project)
        self.library.entries=[LibraryEntry(project,session)];self.library.filter();self.library.tree.selection_set('0');self.library.edit()
        self.assertEqual(self.app.project_path,str(project))
        self.app.session.model.output_gain_db=-2;self.app.changed();self.assertTrue(self.app.save_project())
        from irbq.project import Session
        self.assertEqual(Session.load(project).model.output_gain_db,-2)

    def test_library_refresh_uses_worker_and_retains_references(self):
        with patch.object(self.app,'run_job') as job:
            self.library.refresh();job.assert_called_once()
            worker,done=job.call_args.args[:2]
            self.assertFalse(Path(self.library.folder.get()).exists())
            result=worker();done(result)
            self.assertTrue(Path(self.library.folder.get()).exists())
            self.assertEqual(self.app.prefs.library_folder,self.library.folder.get())

    def test_edit_updates_same_uid_after_reordering(self):
        self.panel.append(self.model,'A');self.panel.append(self.model,'B')
        self.panel.tree.selection_set('0');self.panel.edit_slot();uid=self.panel.edit_uid
        self.app.session.model.output_gain_db=-4;self.app.changed()
        self.panel.tree.selection_set('0');self.panel.move(1);self.panel.update_slot()
        self.assertEqual(self.panel.project.slots[1].uid,uid);self.assertEqual(self.panel.project.slots[1].model.output_gain_db,-4)
        self.assertEqual(self.panel.project.slots[0].model.output_gain_db,0);self.assertFalse(self.app.dirty)

    def test_model_only_editor_and_save(self):
        self.app.install_session(model_session(self.model));self.app.redraw()
        self.assertIsNone(self.app.session.target);self.assertTrue(self.app.guard_model())
        self.assertGreater(len(self.app.ax.lines),0)
        path=Path(self.temp.name)/'model.irbq'
        with patch('irbq.workspace.filedialog.asksaveasfilename',return_value=str(path)):self.assertTrue(self.app.save_project())
        self.assertTrue(path.exists());self.assertEqual(self.app.prefs.recent_projects,[str(path.resolve())])

    def test_dirty_cancel_and_failed_save_do_not_discard(self):
        self.app.install_session(model_session(self.model));self.app.dirty=True
        with patch('irbq.workspace.messagebox.askyesnocancel',return_value=None):self.assertFalse(self.app.confirm_session())
        self.assertTrue(self.app.dirty)
        with patch('irbq.workspace.messagebox.askyesnocancel',return_value=True),patch.object(self.app,'save_project',return_value=False):
            self.assertFalse(self.app.confirm_session())
        self.panel.dirty=True
        with patch('irbq.zoom_panel.messagebox.askyesnocancel',return_value=None):self.panel.new()
        self.assertTrue(self.panel.dirty)

    def test_all_save_as_overwrite_cancellation_preserves_files(self):
        self.app.install_session(model_session(self.model));self.app.dirty=True
        project=Path(self.temp.name)/'existing.irbq';bank=Path(self.temp.name)/'existing.hybridbank'
        for path in (project,bank):path.write_bytes(b'keep')
        with patch('irbq.workspace.filedialog.asksaveasfilename',return_value=str(project)),patch('irbq.workspace.messagebox.askyesno',return_value=False):
            self.assertFalse(self.app.save_project(True))
        self.assertTrue(self.app.dirty);self.assertEqual(project.read_bytes(),b'keep')
        self.panel.dirty=True
        with patch('irbq.zoom_panel.filedialog.asksaveasfilename',return_value=str(bank)),patch('irbq.zoom_panel.messagebox.askyesno',return_value=False):
            self.assertFalse(self.panel.save(True))
        self.assertTrue(self.panel.dirty);self.assertEqual(bank.read_bytes(),b'keep')
        with patch('irbq.library_panel.filedialog.asksaveasfilename',return_value=str(project)),patch('irbq.library_panel.messagebox.askyesno',return_value=False),patch.object(self.library,'refresh') as refresh:
            self.library.save_current();refresh.assert_not_called()
        self.assertEqual(project.read_bytes(),b'keep')

    def test_bank_navigation_cancel_preserves_unapplied_edit_binding(self):
        self.panel.append(self.model,'A');self.panel.tree.selection_set('0');self.panel.edit_slot()
        self.panel.dirty=False;self.app.session.model.output_gain_db=-4;self.app.changed()
        previous=self.panel.project;uid=self.panel.edit_uid
        with patch('irbq.workspace.messagebox.askyesnocancel',return_value=None):
            self.panel.new();self.panel.open('unused.hybridbank')
        self.assertIs(self.panel.project,previous);self.assertEqual(self.panel.edit_uid,uid)
        self.assertTrue(self.app.dirty);self.assertEqual(self.app.session.model.output_gain_db,-4)

    def test_bank_navigation_discard_restores_slot_instead_of_orphaning_edit(self):
        from irbq.zoom_bank import BankProject
        path=Path(self.temp.name)/'new.hybridbank';BankProject().save(path)
        for action in (self.panel.new,lambda:self.panel.open(path)):
            self.panel.append(self.model,'A');self.panel.tree.selection_set('0');self.panel.edit_slot()
            self.panel.dirty=False;self.app.session.model.output_gain_db=-4;self.app.changed()
            with patch('irbq.workspace.messagebox.askyesnocancel',return_value=False):action()
            self.assertFalse(self.app.dirty);self.assertIsNone(self.panel.edit_uid)
            self.assertEqual(self.app.session.model.output_gain_db,0)
            self.assertEqual(self.panel.project.slots,[])

    def test_bank_discard_then_bank_cancel_keeps_restored_binding(self):
        self.panel.append(self.model,'A');self.panel.tree.selection_set('0');self.panel.edit_slot()
        uid=self.panel.edit_uid;old=self.panel.project
        self.app.session.model.output_gain_db=-4;self.app.changed()
        with patch('irbq.workspace.messagebox.askyesnocancel',side_effect=[False,None]):self.panel.new()
        self.assertIs(self.panel.project,old);self.assertEqual(self.panel.edit_uid,uid)
        self.assertFalse(self.app.dirty);self.assertEqual(self.app.session.model.output_gain_db,0)

    def test_theme_preserves_library_and_edit_binding(self):
        self.panel.append(self.model,'A');self.panel.tree.selection_set('0');self.panel.edit_slot()
        uid=self.panel.edit_uid;self.library.query.set('cab');self.library.taps.set('128')
        self.assertTrue(self.app.apply_preferences('ru','light'));self.app.update()
        self.assertEqual(self.app.zoom_panel.edit_uid,uid);self.assertEqual(self.app.library_panel.query.get(),'cab')
        self.assertEqual(self.app.library_panel.taps.get(),'128')

    def test_bank_table_has_real_working_height(self):
        # Assert layout at an explicit desktop size, not the runner's screen default.
        self.app.maxsize(1920,1200)
        self.app.geometry('1440x930');self.app.update()
        if self.app.winfo_height()<900:
            self.skipTest('Window manager cannot supply the 1440x930 layout-test surface')
        print('Layout dimensions:',self.app.winfo_geometry(),self.app.winfo_screenwidth(),self.app.winfo_screenheight(),flush=True)
        self.app.tabs.select(self.panel);self.app.update();self.app.catalog_selected();self.app.update()
        self.assertGreater(self.panel.tree.winfo_height(),200)
        self.assertLess(self.panel.budget_frame.winfo_width(),500)
        self.assertGreater(self.panel.tree.winfo_width(),300)
        self.app.geometry('1100x740');self.app.update();self.app._catalog_active=False;self.app.catalog_selected();self.app.update()
        self.assertGreater(self.panel.tree.winfo_height(),120)
        self.assertGreater(self.app.canvas.get_tk_widget().winfo_height(),200)
        self.assertLess(abs(self.app.split.sashpos(0)/self.app.split.winfo_height()-.5),.01)
        self.app.tabs.select(self.library);self.app.update()
        self.assertGreater(self.library.tree.winfo_height(),140)
        self.assertEqual(self.errors,[])


if __name__=='__main__':unittest.main()
