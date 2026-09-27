"""Regression tests for the shared graph, inspector and persistent localisation/theme."""
import os
import copy
import json
import time
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from irbq.preferences import Preferences,load_preferences,save_preferences
from irbq.i18n import tr,set_language,trf

class TestPreferences(unittest.TestCase):
    def tearDown(self):set_language('ru')
    def test_defaults_and_invalid_file(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'prefs.json'
            self.assertEqual(load_preferences(p),Preferences())
            p.write_text('{broken',encoding='utf-8');self.assertEqual(load_preferences(p),Preferences())
            p.write_text(json.dumps({'language':'x','theme':'pink','edit_enabled':'true'}));q=load_preferences(p)
            self.assertEqual(q.language,'en');self.assertEqual(q.theme,'dark');self.assertFalse(q.edit_enabled)
    def test_atomic_roundtrip(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'new'/'settings.json';a=Preferences('en','dark',True,False,True)
            save_preferences(a,p);self.assertEqual(load_preferences(p),a)
            self.assertEqual(len(list(p.parent.iterdir())),1)
    def test_static_and_dynamic_localisation(self):
        set_language('en')
        self.assertEqual(tr('Настройки'),'Settings')
        self.assertEqual(trf('Исходник: {0} отсч., {1} Hz.',512,44100),'Source: 512 samples, 44100 Hz.')
        self.assertEqual(tr('Исходник: 512 отсч., 44100 Hz.'),'Source: 512 samples, 44100 Hz.')
        set_language('ru');self.assertEqual(tr('Source: 512 samples, 44100 Hz.'),'Исходник: 512 отсч., 44100 Hz.')

@unittest.skipUnless(os.environ.get('DISPLAY') or os.name=='nt','requires GUI display')
class TestWorkspace(unittest.TestCase):
    def setUp(self):
        from irbq.gui import App
        from irbq.project import Session
        from irbq.dsp import Model,PrepConfig,Biquad
        self.tmp=tempfile.TemporaryDirectory()
        self.patch=patch.dict(os.environ,{'IRBQ_SETTINGS_PATH':str(Path(self.tmp.name)/'settings.json')});self.patch.start()
        self.app=App();self.errors=[];self.app.error=lambda e:self.errors.append(str(e))
        self.app.report_callback_exception=lambda et,e,tb:self.errors.append(str(e))
        a=self.app
        a.session=Session(source=np.r_[1.,.2,np.zeros(800)],source_fs=44100,config=PrepConfig(fs=44100,minimum_phase=False,trim_start=False))
        a.session.preprocess()
        b=Biquad('Peak','Resonance',123.4567890123,.743219876,3.23456789)
        c=Biquad('HighShelf','Presence',3800,.7,0.,locked=True,qmax=1.)
        a.session.model=Model(44100,np.r_[1.,np.zeros(63)],[b,c],'UI test')
        a.sync_prep();a.changed();a.update();a.redraw();a.update();a.canvas.draw()
    def tearDown(self):
        a=self.app;a.dirty=False
        try:a.close()
        finally:self.patch.stop();self.tmp.cleanup();set_language('ru')
        self.assertFalse(self.errors,self.errors)
    def flush(self):
        for _ in range(4):self.app.update();time.sleep(.06)
        self.app.redraw();self.app.update();self.app.canvas.draw()
    def test_single_canvas_and_independent_overlays(self):
        a=self.app
        self.assertIs(a.canvas,a.eqcanvas);self.assertIs(a.ax,a.eqax)
        a.edit_enabled.set(False);a.show_bands.set(False);a.show_bq_sum.set(False);a.overlay_changed();self.flush()
        self.assertFalse(a.eq_handle_xy);self.assertEqual(len(a.figure.axes),1)
        a.show_bands.set(True);a.overlay_changed();self.flush()
        self.assertFalse(a.eq_handle_xy);self.assertEqual(len(a.figure.axes),2)
        self.assertEqual(sum(line.get_gid()=='individual-bq' for line in a.band_ax.lines),2)
        a.show_bands.set(False);a.edit_enabled.set(True);a.overlay_changed();self.flush()
        self.assertEqual(len(a.eq_handle_xy),2);self.assertEqual(len(a.figure.axes),1)
        a.plotvar.set('ФЧХ: без выравнивания');a.on_plot_mode();self.flush();self.assertFalse(a.eq_handle_xy)
    def test_sliders_work_with_handles_hidden_undo_and_fir_preserved(self):
        a=self.app;a.edit_enabled.set(False);a.bqtree.selection_set('0');a.sync_eq_quick()
        h=a.session.model.fir.copy();before=a.session.model.sections[0].gain
        a.slider_begin();a.slider_changed('gain',.7);a.slider_changed('gain',.73);a.slider_end()
        self.assertGreater(a.session.model.sections[0].gain,before)
        np.testing.assert_array_equal(h,a.session.model.fir)
        self.assertEqual(len(a.undo_stack),1)
        a.undo();self.assertEqual(a.session.model.sections[0].gain,before)
    def test_exact_coefficients_not_rounded_by_focus_or_flags(self):
        a=self.app;b=a.session.model.sections[0];b.raw=b.coefficients(44100).tolist()
        orig=b.to_dict();a.bqtree.selection_set('0');a.sync_eq_quick();a.eq_quick_apply()
        self.assertEqual(a.session.model.sections[0].to_dict(),orig)
        a.eq_lock.set(True);a.eq_quick_apply();out=a.session.model.sections[0]
        self.assertEqual(out.f,orig['f']);self.assertEqual(out.q,orig['q']);self.assertEqual(out.raw,orig['raw'])
        a.eq_on.set(False);a.eq_quick_apply();self.assertEqual(out.raw,orig['raw'])
    def test_actual_graph_drag_wheel_and_bypass_events(self):
        from matplotlib.backend_bases import MouseEvent
        a=self.app;a.edit_enabled.set(True);a.overlay_changed();self.flush()
        x,y=a.ax.transData.transform(a.eq_handle_xy[0]);before=a.session.model.sections[0].to_dict();n=len(a.undo_stack)
        ev=MouseEvent('button_press_event',a.canvas,x,y,button=1);a.eq_press(ev)
        a.eq_motion(MouseEvent('motion_notify_event',a.canvas,x+28,y+12,button=1));a.eq_release(MouseEvent('button_release_event',a.canvas,x+28,y+12,button=1));self.flush()
        self.assertNotEqual(a.session.model.sections[0].f,before['f']);self.assertEqual(len(a.undo_stack),n+1)
        q=a.session.model.sections[0].q;x,y=a.ax.transData.transform(a.eq_handle_xy[0]);a.eq_scroll(MouseEvent('scroll_event',a.canvas,x,y,button='up',step=1));self.assertGreater(a.session.model.sections[0].q,q)
        self.flush();x,y=a.ax.transData.transform(a.eq_handle_xy[0]);a.eq_press(MouseEvent('button_press_event',a.canvas,x,y,button=1,dblclick=True));self.assertFalse(a.session.model.sections[0].enabled)
    def test_edit_off_blocks_events_and_busy_blocks_edit(self):
        from matplotlib.backend_bases import MouseEvent
        a=self.app;a.edit_enabled.set(True);a.overlay_changed();self.flush();x,y=a.ax.transData.transform(a.eq_handle_xy[0])
        before=a.session.model.to_dict()
        a.edit_enabled.set(False);a.eq_scroll(MouseEvent('scroll_event',a.canvas,x,y,button='up',step=1));a.eq_press(MouseEvent('button_press_event',a.canvas,x,y,button=1,dblclick=True))
        self.assertEqual(a.session.model.to_dict(),before)
        a.edit_enabled.set(True);a.busy=True
        a.slider_changed('gain',.9);a.eq_scroll(MouseEvent('scroll_event',a.canvas,x,y,button='up',step=1));a.busy=False
        self.assertEqual(a.session.model.to_dict(),before)
    def test_language_theme_state_and_project_invariant(self):
        a=self.app;a.pvars['normalization'].set('Пик импульса');a.mode.set('Только BQ (с текущим состоянием FIR)');a.objective.set('Магнитуда dB (только BQ)');a.fit_gain.set(False);a.plotvar.set('ΔАЧХ: модель − эталон');a.fitvars['iterations'].set('17');a.bqtree.selection_set('1')
        a.session.snapshots.append(a.session.model.clone());a.refresh_snapshots();a.stree.selection_set('0')
        before=a.session.model.to_dict();dirty=a.dirty
        self.assertTrue(a.apply_preferences('en','dark'));self.flush()
        self.assertEqual(a.session.model.to_dict(),before);self.assertEqual(a.dirty,dirty);self.assertEqual(a.fitvars['iterations'].get(),'17')
        self.assertEqual(a.read_prep().normalization,'peak');cfg=a.train_config();self.assertEqual(cfg.mode,'bq');self.assertEqual(cfg.objective,'magnitude');self.assertFalse(cfg.fit_gain)
        self.assertEqual(a.plotvar.get(),'ΔАЧХ: модель − эталон');self.assertEqual(a.selected_bq(),1);self.assertEqual(a.stree.selection(),('0',))
        self.assertEqual(a.prefs.theme,'dark');self.assertEqual(a.colors['bg'],'#171c23')
        self.assertEqual(load_preferences().language,'en')
        self.assertTrue(a.apply_preferences('ru','light'));self.flush();self.assertEqual(a.session.model.to_dict(),before)
    def test_entire_english_ui_and_advanced_dialog(self):
        import tkinter as tk
        from irbq.gui import BQEditor
        a=self.app;a.apply_preferences('en','dark');self.flush()
        texts=[]
        def walk(w):
            try:texts.append(str(w.cget('text')))
            except tk.TclError:pass
            if w.winfo_class()=='TCombobox':texts.extend(w.cget('values'))
            if w.winfo_class()=='TNotebook':texts.extend(w.tab(t,'text') for t in w.tabs())
            for child in w.winfo_children():walk(child)
        a.edit_bq();a.update()
        walk(a)
        bad=[t for t in texts if re.search('[А-Яа-яЁё]',str(t)) and t!='Русский']
        self.assertFalse(bad,bad)
        for w in a.winfo_children():
            if isinstance(w,tk.Toplevel):w.destroy()
        a.language_choice.set('Русский');a.language_selector.event_generate('<<ComboboxSelected>>')
        self.flush();self.assertEqual(a.prefs.language,'ru')
        a.appearance_controls[1].invoke();self.flush();self.assertEqual(a.prefs.theme,'light')

    def test_header_defaults_colors_and_preview_lifecycle(self):
        a=self.app
        self.assertEqual((a.prefs.language,a.prefs.theme),('en','dark'))
        self.assertEqual(a.colors['ref'],'#e2b66d');self.assertEqual(a.colors['model'],'#6ab8ff')
        original=a.session.model;candidate=original.clone();candidate.sections[0].gain=12
        a.busy=True
        for i in range(10):a.publish_training_preview(candidate.clone())
        self.assertEqual(a.preview_events.qsize(),1)
        self.flush()
        self.assertIs(a.session.model,original);self.assertIsNotNone(a.training_preview)
        f,T=a.target_response()
        from irbq.dsp import db
        np.testing.assert_allclose(a.ax.lines[1].get_ydata(),db(candidate.response(f)))
        a.events.put(('cancelled',None));self.flush()
        self.assertIsNone(a.training_preview);self.assertTrue(a.preview_events.empty())
        self.assertIs(a.session.model,original)
        a.open_settings();a.update()
        import tkinter as tk
        self.assertFalse(any(isinstance(w,tk.Toplevel) for w in a.winfo_children()))

    def test_english_menus_dialogs_logs_choices_and_plots(self):
        import tkinter as tk
        a=self.app;a.apply_preferences('en','dark');self.flush()
        a.log('Исходник: 512 отсч., 44100 Hz.\nЯвная инверсия полярности (после MPT).\nИмпорт: точные SOS, включая float32 исходного runtime.')
        a.graph_options();a.update()
        texts=[]
        def walk(w):
            for option in ('text','title'):
                try:texts.append(str(w.cget(option)))
                except tk.TclError:pass
            if isinstance(w,tk.Toplevel):texts.append(w.title())
            if isinstance(w,tk.Menu):
                for i in range((w.index('end') or 0)+1):
                    try:texts.append(w.entrycget(i,'label'))
                    except tk.TclError:pass
            if w.winfo_class()=='Text':texts.append(w.get('1.0','end'))
            if w.winfo_class()=='TCombobox':texts.extend(w.cget('values'));texts.append(w.get())
            if w.winfo_class()=='TNotebook':texts.extend(w.tab(t,'text') for t in w.tabs())
            if w.winfo_class()=='Treeview':
                texts.extend(w.heading(c,'text') for c in w.cget('columns'))
            for child in w.winfo_children():walk(child)
        walk(a)
        for mode in __import__('irbq.gui',fromlist=['PLOTS']).PLOTS:
            a.plotvar.set(mode);a.redraw();a.update()
            texts.extend([a.ax.get_title(loc='left'),a.ax.get_xlabel(),a.ax.get_ylabel()])
            texts.extend(a.ax.get_legend_handles_labels()[1])
        with patch('irbq.workspace.messagebox.showinfo') as show:
            a.show_help();texts.extend(str(v) for v in show.call_args.args)
        bad=[t for t in texts if re.search('[А-Яа-яЁё]',str(t)) and t!='Русский']
        self.assertFalse(bad,bad)
    def test_worker_preview_success_and_error_cleanup(self):
        import threading
        a=self.app;original=a.session.model;candidate=original.clone()
        candidate.sections[0].gain=8
        main_thread=threading.get_ident();worker_ids=[];callback_ids=[]
        release=threading.Event()
        def task():
            worker_ids.append(threading.get_ident())
            a.publish_training_preview(candidate)
            if not release.wait(5):raise RuntimeError('test worker timed out')
            return candidate
        def done(value):
            callback_ids.append(threading.get_ident());a.session.model=value
        try:
            a.run_job(task,done,'Preview test')
            self.assertTrue(all('disabled' in w.state() for w in a.appearance_controls))
            deadline=time.monotonic()+3
            while a.training_preview is None and time.monotonic()<deadline:a.update();time.sleep(.02)
            self.assertIs(a.training_preview,candidate);self.assertIs(a.session.model,original)
        finally:release.set()
        deadline=time.monotonic()+3
        while a.busy and time.monotonic()<deadline:a.update();time.sleep(.02)
        self.assertFalse(a.busy);self.assertIsNone(a.training_preview)
        self.assertEqual(callback_ids,[main_thread]);self.assertNotEqual(worker_ids,[main_thread])
        self.assertTrue(all('disabled' not in w.state() for w in a.appearance_controls))
        self.assertIn('readonly',a.language_selector.state())
        a.busy=True;a.publish_training_preview(original)
        a.events.put(('error',('expected test error','expected test traceback')))
        self.flush();self.assertIsNone(a.training_preview);self.assertTrue(a.preview_events.empty())
        self.assertEqual(self.errors,['expected test error']);self.errors.clear()
        self.assertIs(a.session.model,candidate)

    def test_fir_bypass_then_refit_after_theme_change(self):
        a=self.app;a.fir_enabled.set(False);a.toggle_fir_path();h=a.session.model.fir.copy();a.apply_preferences('en','dark');self.flush()
        self.assertFalse(a.session.model.fir_enabled);np.testing.assert_array_equal(h,a.session.model.fir)
        a.fitvars['iterations'].set('3');a.greedy.set(False);a.start_train('bq')
        deadline=time.monotonic()+15
        while a.busy and time.monotonic()<deadline:a.update();time.sleep(.02)
        self.assertFalse(a.busy);np.testing.assert_array_equal(h,a.session.model.fir)
        a.enable_and_refit_fir()
        deadline=time.monotonic()+15
        while a.busy and time.monotonic()<deadline:a.update();time.sleep(.02)
        self.assertFalse(a.busy);self.assertTrue(a.session.model.fir_enabled)

    def test_overall_gain_editor_and_auto_objective(self):
        a=self.app
        before=a.session.model.response(np.array([1000.]))[0]
        a.output_gain_text.set('-6');a.output_gain_apply();a.update()
        self.assertAlmostEqual(a.session.model.output_gain_db,-6.0)
        after=a.session.model.response(np.array([1000.]))[0]
        self.assertAlmostEqual(abs(after/before),10**(-6/20),places=10)
        a.objective.set('Авто (рекомендуется)');a.fit_gain.set(True);a.mode.set('Только BQ (с текущим состоянием FIR)')
        cfg=a.train_config();self.assertEqual(cfg.objective,'auto');self.assertTrue(cfg.fit_gain)
        a.undo();self.assertAlmostEqual(a.session.model.output_gain_db,0.0)

    def test_wheel_scroll_and_stable_notebook_style(self):
        from types import SimpleNamespace
        from tkinter import ttk
        a=self.app;a.options.select(1);a.update_idletasks()
        panel=a.fit_scroll;panel.canvas.yview_moveto(0);a.update_idletasks();before=panel.canvas.yview()
        panel._route_wheel(SimpleNamespace(delta=-120,num=None,widget=panel.body));a.update_idletasks();after=panel.canvas.yview()
        self.assertGreaterEqual(after[0],before[0])
        maps=ttk.Style(a).map('TNotebook.Tab')
        self.assertIn('expand',maps);self.assertIn('padding',maps)
        self.assertTrue(all(tuple(v) == (0,0,0,0) if not isinstance(v,str) else v == '0 0 0 0' for _,v in maps['expand']))

    def test_all_plot_modes_both_themes(self):
        from irbq.gui import PLOTS
        a=self.app
        for language,theme in [('en','dark'),('ru','light')]:
            a.apply_preferences(language,theme)
            for mode in PLOTS:
                a.plotvar.set(mode);a.redraw();a.update()
                self.assertTrue(a.figure.axes)
        self.assertFalse(self.errors,self.errors)

if __name__=='__main__':unittest.main(verbosity=2)
