"""Unified response workspace: optional editing overlays, inspector, languages and themes.

Only authoring/presentation changes live here. FIR/BQ equations and trainer stay separate.
"""
from __future__ import annotations
import copy
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import numpy as np
from scipy import ndimage
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from .i18n import tr as _, trf as _tf, ChoiceVar, DisplayVar, set_language, get_language
from .preferences import load_preferences, save_preferences
from .ui_theme import apply_theme, theme_axes, theme_widgets
from .dsp import KINDS, Biquad, db, sos_response, sos_array, fir_response, response_metrics, phase_diagnostics, sos_stability, frequency_grid
from . import __version__

PLOTS=['АЧХ','ΔАЧХ: модель − эталон','ФЧХ: без выравнивания','ΔФЧХ: относительно эталона',
       'Групповая задержка','Импульс','BQ по секциям','Комплексная разность Hmodel − Href']
EDIT_PLOTS=(PLOTS[0],PLOTS[1],PLOTS[6])

class QuietToolbar(NavigationToolbar2Tk):
    """Matplotlib navigation backend with a compact, translated application toolbar."""
    toolitems=()
    def set_message(self,s):
        # No unlocalised Matplotlib help/coordinates are shown in the application UI.
        pass

class WorkspaceMixin:
    def __init__(self):
        self.prefs=load_preferences()
        set_language(self.prefs.language)
        self._sync_controls=False
        self._slider_active=False
        self._slider_saved=False
        self._wheel_band=None
        self._view_locked=False
        self._metrics_due=True
        self._gain_slider_active=False
        self._gain_slider_saved=False
        super().__init__()
        if getattr(self.prefs, 'prep_defaults', None):
            self.load_prep_defaults(silent=True)
        screen_w=max(800,int(self.winfo_screenwidth()))
        screen_h=max(600,int(self.winfo_screenheight()))
        # Leave room for the window-manager title bar/panel and force an explicit
        # on-screen origin. This matters in Codespaces/noVNC where the virtual
        # desktop can be smaller than the normal 1440x930 desktop layout.
        margin_x=40
        margin_y=100
        width=min(1440,max(760,screen_w-margin_x))
        height=min(930,max(560,screen_h-margin_y))
        min_width=min(1100,max(640,screen_w-margin_x))
        min_height=min(740,max(480,screen_h-margin_y))
        self.minsize(min_width,min_height)
        self.geometry(f'{width}x{height}+10+10')
        apply_theme(self,self.prefs.theme)
        self.redraw()

    def _make_ui(self):
        self.colors=apply_theme(self,self.prefs.theme)
        self.eq_drag=None;self.eq_handle_xy=[];self.eq_last_wheel=0.
        self._slider_active=False;self._slider_saved=False
        self._make_menu()
        header=ttk.Frame(self,padding=(12,8));header.pack(fill='x')
        ttk.Label(header,text='IRBQ Lab',style='Title.TLabel').pack(side='left')
        ttk.Label(header,text=f'  {__version__}  /  IR · FIR · BQ',style='Small.TLabel').pack(side='left',padx=8)
        appearance=ttk.Frame(header);appearance.pack(side='right')
        ttk.Label(appearance,text='🌐',font=('Segoe UI Symbol',14)).pack(side='left',padx=(0,6))
        self.language_choice=tk.StringVar(value='English' if self.prefs.language=='en' else 'Русский')
        self.language_selector=ttk.Combobox(appearance,textvariable=self.language_choice,
            values=['English','Русский'],state='readonly',width=9)
        self.language_selector.pack(side='left',padx=(0,12))
        self.language_selector.bind('<<ComboboxSelected>>',lambda e:self.apply_preferences(
            'en' if self.language_choice.get()=='English' else 'ru',self.prefs.theme))
        self.appearance_controls=[self.language_selector]
        for theme,icon in [('light','☀'),('dark','☾')]:
            button=ttk.Button(appearance,text=icon,width=3,
                style='Accent.TButton' if self.prefs.theme==theme else 'TButton',
                command=lambda t=theme:self.apply_preferences(self.prefs.language,t))
            button.pack(side='left',padx=2);self.appearance_controls.append(button)
        self.file_label=ttk.Label(header,text=_('WAV не загружен'),style='Small.TLabel');self.file_label.pack(side='right',padx=14)
        bar=ttk.Frame(self,padding=(10,0,10,8));bar.pack(fill='x')
        self.action_buttons=[]
        for label,cmd in [('Открыть WAV',self.open_wav),('Подготовить IR',self.preprocess),('Обучить',self.start_train),
                          ('Пересчитать FIR',self.refit_fir),('Снимок модели',self.snapshot),('Экспорт',self.export)]:
            b=ttk.Button(bar,text=_(label),command=cmd,style='Accent.TButton' if label=='Обучить' else 'TButton')
            b.pack(side='left',padx=3);self.action_buttons.append(b)
        for label,cmd in [('Открыть проект…',self.open_project),('Сохранить проект',self.save_project)]:
            b=ttk.Button(bar,text=_(label),command=cmd);b.pack(side='left',padx=3);self.action_buttons.append(b)
        self.tools_button=ttk.Button(bar,text=_('Скрыть инструменты'),command=self.toggle_tools);self.tools_button.pack(side='right',padx=3)
        ttk.Button(bar,text=_('СТОП'),command=self.cancel).pack(side='right',padx=3)
        self.mainpane=ttk.Panedwindow(self,orient='horizontal');self.mainpane.pack(fill='both',expand=True,padx=10)
        self.tools_panel=ttk.Frame(self.mainpane,width=298);self.right_panel=ttk.Frame(self.mainpane)
        self.mainpane.add(self.tools_panel,weight=0);self.mainpane.add(self.right_panel,weight=1)
        self._tools_visible=True
        from .gui import ScrollPanel
        self.options=ttk.Notebook(self.tools_panel);self.options.pack(fill='both',expand=True)
        prep=ScrollPanel(self.options);fit=ScrollPanel(self.options);self.prep_scroll=prep;self.fit_scroll=fit
        self.options.add(prep,text=_('Подготовка'));self.options.add(fit,text=_('Обучение'))
        self._prep_ui(prep.body);self._fit_ui(fit.body)
        self._compact_sidebar(prep.body);self._compact_sidebar(fit.body)
        prep.bind_wheel_tree();fit.bind_wheel_tree()
        self.split=ttk.Panedwindow(self.right_panel,orient='vertical');self.split.pack(fill='both',expand=True)
        plotbox=ttk.Frame(self.split);lower=ttk.Frame(self.split)
        self.plot_panel=plotbox;self.detail_panel=lower
        self.split.add(plotbox,weight=5);self.split.add(lower,weight=1)
        self._plot_ui(plotbox)
        self.tabs=ttk.Notebook(lower);self.tabs.pack(fill='both',expand=True)
        filters=ttk.Frame(self.tabs,padding=8);allbands=ttk.Frame(self.tabs,padding=5)
        variants=ttk.Frame(self.tabs,padding=5);listen=ttk.Frame(self.tabs,padding=8);info=ttk.Frame(self.tabs,padding=5)
        for frame,label in [(filters,'Фильтр'),(allbands,'Все BQ'),(variants,'Варианты / A–B'),(listen,'Прослушивание'),(info,'Метрики / журнал')]:
            self.tabs.add(frame,text=_(label))
        self._filters_ui(filters);self._all_bands_ui(allbands);self._variants_ui(variants);self._listen_ui(listen)
        from .zoom_panel import ZoomPanel
        self.zoom_panel=ZoomPanel(self,self.tabs)
        self.tabs.add(self.zoom_panel,text='Zoom ZDL')
        from .library_panel import LibraryPanel
        self.library_panel=LibraryPanel(self,self.tabs)
        self.tabs.add(self.library_panel,text=_('Library'))
        self._catalog_active=False;self._trainer_sash=None
        self.tabs.bind('<<NotebookTabChanged>>',self.catalog_selected,add='+')
        self.metrics_label=ttk.Label(info,text=_('Метрики появятся после подготовки WAV.'),justify='left',font=('Consolas',9))
        self.metrics_label.pack(fill='x',anchor='w',padx=6,pady=3)
        logframe=ttk.Frame(info);logframe.pack(fill='both',expand=True)
        self.logtext=tk.Text(logframe,height=4,wrap='word',font=('Consolas',9));self.logtext.pack(side='left',fill='both',expand=True)
        logscroll=ttk.Scrollbar(logframe,orient='vertical',command=self.logtext.yview);logscroll.pack(side='right',fill='y');self.logtext.configure(yscrollcommand=logscroll.set)
        self._bind_wheel_scroll(self.logtext,self.logtext)
        foot=ttk.Frame(self,padding=(10,5));foot.pack(side='bottom',fill='x',before=self.mainpane)
        self.status=DisplayVar(value=_('Откройте WAV → подготовьте IR → создайте структуру или импортируйте модель.'))
        ttk.Label(foot,textvariable=self.status,style='Small.TLabel',wraplength=1100).pack(side='left',fill='x',expand=True)
        self.progress=ttk.Progressbar(foot,maximum=100,length=160);self.progress.pack(side='right')
        self.after_idle(self._initial_sashes)
        theme_widgets(self,self.colors)

    def _initial_sashes(self):
        try:
            self.mainpane.sashpos(0,300)
            height=self.split.winfo_height()
            self.split.sashpos(0,max(290,height-218))
            self.catalog_selected()
        except tk.TclError:pass

    def expand_catalog(self):
        self.split.pane(self.plot_panel,weight=1);self.split.pane(self.detail_panel,weight=1)
        if not self._catalog_active:
            self._trainer_sash=self.split.sashpos(0)
            self._catalog_active=True
            self.split.sashpos(0,int(self.split.winfo_height()*.5))

    def catalog_selected(self,event=None):
        if not hasattr(self,'library_panel'):return
        current=self.tabs.select()
        if current in (str(self.zoom_panel),str(self.library_panel)):
            self.expand_catalog()
            if current==str(self.library_panel):self.library_panel.ensure_loaded()
        elif self._catalog_active:
            self._catalog_active=False
            self.split.pane(self.plot_panel,weight=5);self.split.pane(self.detail_panel,weight=1)
            if self._trainer_sash is not None:self.split.sashpos(0,self._trainer_sash)

    def remember_path(self,field,path):
        paths=getattr(self.prefs,field)
        path=str(Path(path).resolve())
        setattr(self.prefs,field,[path]+[p for p in paths if p!=path][:9])
        if field=='recent_projects':self.refresh_recent_projects()
        self._save_settings_quietly()

    def refresh_recent_projects(self):
        if not hasattr(self,'recent_projects_menu'):return
        self.recent_projects_menu.delete(0,'end')
        for path in self.prefs.recent_projects:
            self.recent_projects_menu.add_command(label=Path(path).name,command=lambda p=path:self.open_project(p))

    def confirm_session(self,discard=None):
        if not self.dirty:return True
        answer=messagebox.askyesnocancel(_('IRBQ project'),_('Save project changes before continuing?'),parent=self)
        if answer is True:return self.save_project()
        if answer is False:
            if discard:discard()
            return True
        return False

    def install_session(self,session,path=None):
        self.player.stop();self.audio_render=None;self.training_preview=None
        self.session=session;self.project_path=str(path) if path else None
        self.target_cache={};self.undo_stack=[];self.redo_stack=[]
        self.zoom_panel.edit_uid=None;self.zoom_panel.edit_digest=None;self.zoom_panel.refresh_titles()
        self.sync_prep();self.refresh_snapshots();self.changed();self.dirty=False
        if session.target is None:self.plotvar.set(PLOTS[0])
        self.file_label.configure(text=Path(path).name if path else (session.source_name or _('Model without reference')))

    def save_active(self):
        if self.tabs.select()==str(self.zoom_panel):return self.zoom_panel.guarded(self.zoom_panel.save)
        return self.save_project()

    def save_project(self,save_as=False):
        if not self.guard_model():return False
        path=self.project_path
        choose=save_as or not path
        if choose:
            path=filedialog.asksaveasfilename(parent=self,defaultextension='.irbq',filetypes=[('IRBQ project','*.irbq')],
                initialfile=Path(path).name if path else 'Cabinet.irbq',confirmoverwrite=False)
        if not path:return False
        if choose and Path(path).exists() and not messagebox.askyesno(_('Replace project?'),str(path),parent=self):return False
        try:
            self.session.save(path);self.project_path=str(path);self.dirty=False
            self.remember_path('recent_projects',path)
            self.file_label.configure(text=Path(path).name);self.status.set(_('Project saved: {path}').format(path=path))
            return True
        except Exception as exc:self.error(exc);return False

    def open_project(self,path=None):
        if not self.guard(False):return
        path=path or filedialog.askopenfilename(parent=self,filetypes=[('IRBQ project','*.irbq')])
        if not path:return
        try:
            from .project import Session
            session=Session.load(path)
            if not self.confirm_session():return
            self.install_session(session,path);self.remember_path('recent_projects',path)
        except Exception as exc:self.error(exc)

    def attach_reference(self):
        if not self.guard_model():return
        path=filedialog.askopenfilename(parent=self,filetypes=[('Audio','*.wav *.flac *.aif *.aiff')])
        if not path:return
        # Keep the fitted model; a new WAV supplies a real target, never a synthesized one.
        from .project import Session
        cfg=copy.deepcopy(self.session.config);model=self.session.model.clone()
        snapshots=copy.deepcopy(self.session.snapshots)
        def task():
            session=Session(config=cfg);session.load_audio(path);session.preprocess()
            session.model=model;session.snapshots=snapshots
            return session
        def done(session):
            binding=(self.zoom_panel.edit_uid,self.zoom_panel.edit_digest)
            previous=self.project_path
            self.install_session(session,previous)
            self.zoom_panel.edit_uid,self.zoom_panel.edit_digest=binding;self.zoom_panel.refresh_titles()
            self.dirty=True
        self.run_job(task,done,'Attach reference WAV')

    def _bind_wheel_scroll(self, widget, target):
        def wheel(event):
            if getattr(event, 'num', None) == 4: units=-1
            elif getattr(event, 'num', None) == 5: units=1
            else:
                delta=getattr(event,'delta',0)
                if not delta:return None
                units=-1 if delta>0 else 1
            try:target.yview_scroll(units*3,'units')
            except tk.TclError:return None
            return 'break'
        widget.bind('<MouseWheel>',wheel,add='+');widget.bind('<Button-4>',wheel,add='+');widget.bind('<Button-5>',wheel,add='+')

    def _compact_sidebar(self,widget):
        shorter={
         _('BQ-only: выключить FIR и обучить BQ'):_('BQ-only: обучить без FIR'),
         _('Включить FIR + пересчитать под текущие BQ'):_('Включить и пересчитать FIR'),
         _('FIR включён в модель / прослушивание'):_('FIR в тракте'),
         _('Только BQ (с текущим состоянием FIR)'):_('Только BQ (с текущим состоянием FIR)')}
        for child in widget.winfo_children():
            if isinstance(child,ttk.Label):child.configure(wraplength=267)
            if isinstance(child,ttk.Button) and child.cget('text') in shorter:child.configure(text=shorter[child.cget('text')])
            self._compact_sidebar(child)

    def _make_menu(self):
        menu=tk.Menu(self);fm=tk.Menu(menu,tearoff=False)
        actions=[('Открыть WAV…',self.open_wav),('Открыть проект…',self.open_project),('Сохранить проект',self.save_project),
                 ('Сохранить проект как…',lambda:self.save_project(True)),('Импорт модели JSON…',self.import_model),
                 ('Импорт таблицы BQ CSV…',self.import_bq),('Экспорт модели…',self.export),('Экспорт всех снимков…',self.export_snapshots),
                 ('Сохранить график PNG…',self.save_plot)]
        for label,cmd in actions:fm.add_command(label=_(label),command=cmd)
        fm.add_command(label=_('Attach reference WAV'),command=self.attach_reference)
        self.recent_projects_menu=tk.Menu(fm,tearoff=False)
        fm.add_cascade(label=_('Recent projects'),menu=self.recent_projects_menu);self.refresh_recent_projects()
        fm.add_separator();fm.add_command(label=_('Выход'),command=self.close);menu.add_cascade(label=_('Файл'),menu=fm)
        em=tk.Menu(menu,tearoff=False);em.add_command(label=_('Отмена действия'),command=self.undo);em.add_command(label=_('Повтор действия'),command=self.redo)
        menu.add_cascade(label=_('Правка'),menu=em)
        hm=tk.Menu(menu,tearoff=False);hm.add_command(label=_('Краткая инструкция'),command=self.show_help);menu.add_cascade(label=_('Справка'),menu=hm)
        self.configure(menu=menu);self.menubar=menu

    def toggle_tools(self):
        if self._tools_visible:
            self.mainpane.forget(self.tools_panel);self.tools_button.configure(text=_('Показать инструменты'))
        else:
            self.mainpane.insert(0,self.tools_panel,weight=0);self.mainpane.sashpos(0,300);self.tools_button.configure(text=_('Скрыть инструменты'))
        self._tools_visible=not self._tools_visible

    def _plot_ui(self,p):
        bar=ttk.Frame(p,padding=(6,4));bar.pack(fill='x')
        self.plotvar=ChoiceVar(value=PLOTS[0],choices=PLOTS)
        self.plot_combo=ttk.Combobox(bar,textvariable=self.plotvar,values=[_(v) for v in PLOTS],state='readonly',width=23)
        self.plot_combo.pack(side='left',padx=(0,10));self.plot_combo.bind('<<ComboboxSelected>>',self.on_plot_mode)
        self.edit_enabled=tk.BooleanVar(value=self.prefs.edit_enabled)
        self.show_bands=tk.BooleanVar(value=self.prefs.show_bands)
        self.show_bq_sum=tk.BooleanVar(value=self.prefs.show_bq_sum)
        for label,var in [('Редактировать',self.edit_enabled),('Отдельные BQ',self.show_bands),('Сумма BQ',self.show_bq_sum)]:
            ttk.Checkbutton(bar,text=_(label),variable=var,command=self.overlay_changed).pack(side='left',padx=5)
        ttk.Button(bar,text=_('Вид…'),command=self.graph_options,width=8).pack(side='right')
        self.showraw=tk.BooleanVar(value=False);self.showpre=tk.BooleanVar(value=False);self.showquant=tk.BooleanVar(value=False)
        self.pure=ChoiceVar(value='Нет',choices=['Нет','512','1024','2048','4096'])
        self.flo=tk.StringVar(value='20');self.fhi=tk.StringVar(value='20000')
        self.smoothing=ChoiceVar(value='Без',choices=['Без','1/24','1/12','1/6','1/3']);self.detrend=tk.BooleanVar(value=False)
        self.figure=Figure(figsize=(10,5),dpi=100,layout='constrained');self.ax=self.figure.add_subplot(111)
        self.band_ax=None
        self.canvas=FigureCanvasTkAgg(self.figure,master=p);self.canvas.get_tk_widget().pack(fill='both',expand=True)
        self.canvas.get_tk_widget().bind('<Configure>',lambda e:self.schedule_plot(),add='+')
        self.canvas.get_tk_widget().bind('<Map>',lambda e:self.after(220,self.schedule_plot),add='+')
        # Compatibility alias: no second canvas / no second response plot.
        self.eqfigure=self.figure;self.eqax=self.ax;self.eqcanvas=self.canvas
        for name,fn in [('button_press_event',self.eq_press),('motion_notify_event',self.eq_motion),('button_release_event',self.eq_release),('scroll_event',self.eq_scroll)]:
            self.canvas.mpl_connect(name,fn)
        self.nav=QuietToolbar(self.canvas,p,pack_toolbar=False);self.nav.pack_forget()
        navrow=ttk.Frame(p,padding=(6,1,6,4));navrow.pack(side='bottom',fill='x',before=self.canvas.get_tk_widget())
        for label,cmd in [('Вписать',self.fit_view),('Лупа',lambda:self.set_navigation('zoom')),('Перемещение',lambda:self.set_navigation('pan'))]:
            ttk.Button(navrow,text=_(label),command=cmd,width=11).pack(side='left',padx=2)
        self.plot_hint=ttk.Label(navrow,text='',style='Small.TLabel',wraplength=750);self.plot_hint.pack(side='left',padx=8,fill='x',expand=True)

    def graph_options(self):
        if hasattr(self,'graph_dialog') and self.graph_dialog.winfo_exists():self.graph_dialog.lift();return
        win=tk.Toplevel(self);self.graph_dialog=win;win.title(_('Диапазон и сравнение'));win.transient(self);win.resizable(False,False)
        box=ttk.Frame(win,padding=18);box.pack(fill='both',expand=True)
        for i,(label,var) in enumerate([('Raw WAV',self.showraw),('До MPT',self.showpre),('Q15 + float32',self.showquant)]):
            ttk.Checkbutton(box,text=_(label),variable=var,command=self.schedule_plot).grid(row=i,column=0,columnspan=2,sticky='w',pady=4)
        row=3
        for label,var,values in [('Pure FIR',self.pure,['Нет','512','1024','2048','4096']),('Сглаживание:',self.smoothing,['Без','1/24','1/12','1/6','1/3'])]:
            ttk.Label(box,text=_(label)).grid(row=row,column=0,sticky='w',pady=7)
            cb=ttk.Combobox(box,values=[_(v) for v in values],textvariable=var,width=18,state='readonly');cb.grid(row=row,column=1,sticky='ew');cb.bind('<<ComboboxSelected>>',lambda e:self.schedule_plot());row+=1
        ttk.Label(box,text=_('От / до Hz:')).grid(row=row,column=0,sticky='w')
        fbox=ttk.Frame(box);fbox.grid(row=row,column=1,sticky='ew')
        for var in (self.flo,self.fhi):
            ent=ttk.Entry(fbox,textvariable=var,width=9);ent.pack(side='left',padx=2);ent.bind('<Return>',lambda e:self.fit_view())
        row+=1
        ttk.Checkbutton(box,text=_('Detrend Δφ (только график)'),variable=self.detrend,command=self.schedule_plot).grid(row=row,column=0,columnspan=2,sticky='w',pady=9);row+=1
        ttk.Label(box,text=_('График не нормализует отдельные кривые. Сглаживание и detrend не меняют звук.'),style='Small.TLabel',wraplength=415).grid(row=row,column=0,columnspan=2,sticky='w',pady=9);row+=1
        ttk.Button(box,text=_('Применить'),command=lambda:(self.fit_view(),win.destroy())).grid(row=row,column=1,sticky='e')
        theme_widgets(win,self.colors)

    def fit_view(self):
        self._view_locked=False;self.eq_drag=None;self.schedule_plot()

    def set_navigation(self,mode):
        if mode=='zoom':self.nav.zoom()
        else:self.nav.pan()
        self.eq_drag=None
        if self.nav.mode:self.edit_enabled.set(False)
        self._view_locked=bool(self.nav.mode);self.overlay_changed(disable_nav=False)

    def on_plot_mode(self,event=None):
        self._view_locked=False;self.eq_drag=None;self.schedule_plot()

    def overlay_changed(self,disable_nav=True):
        self.eq_drag=None
        if disable_nav and self.edit_enabled.get() and self.nav.mode:
            if 'zoom' in str(self.nav.mode):self.nav.zoom()
            else:self.nav.pan()
        self.prefs.edit_enabled=self.edit_enabled.get();self.prefs.show_bands=self.show_bands.get();self.prefs.show_bq_sum=self.show_bq_sum.get()
        self._save_settings_quietly();self.schedule_plot()

    def _filters_ui(self,p):
        grow=ttk.Frame(p);grow.pack(fill='x',pady=(0,8))
        ttk.Label(grow,text=_('Overall Gain')).pack(side='left',padx=(0,8))
        self.output_gain_value=tk.DoubleVar(value=0.0)
        self.output_gain_slider=ttk.Scale(grow,orient='horizontal',from_=-60,to=60,variable=self.output_gain_value,command=self.output_gain_changed)
        self.output_gain_slider.pack(side='left',fill='x',expand=True,padx=4)
        self.output_gain_slider.bind('<ButtonPress-1>',self.output_gain_begin,add='+');self.output_gain_slider.bind('<ButtonRelease-1>',self.output_gain_end,add='+')
        self.output_gain_text=tk.StringVar(value='0.000')
        ge=ttk.Entry(grow,textvariable=self.output_gain_text,width=9,justify='center');ge.pack(side='left',padx=4)
        ge.bind('<Return>',lambda e:self.output_gain_apply());ge.bind('<FocusOut>',lambda e:self.output_gain_apply())
        ttk.Label(grow,text='dB').pack(side='left')
        ttk.Button(grow,text='0 dB',command=self.output_gain_zero,width=6).pack(side='left',padx=(7,0))
        self.output_gain_entry=ge
        row=ttk.Frame(p);row.pack(fill='x',pady=(0,7))
        # The band selector itself identifies the selection; avoid a redundant label.
        self.band_choice=tk.StringVar();self.band_selector=ttk.Combobox(row,textvariable=self.band_choice,state='readonly',width=22)
        self.band_selector.pack(side='left',padx=(0,8));self.band_selector.bind('<<ComboboxSelected>>',self.select_band_combo)
        self.eq_kind=ChoiceVar(value='Peak',choices=KINDS);self.eq_kind_combo=ttk.Combobox(row,textvariable=self.eq_kind,values=[_(v) for v in KINDS],state='readonly',width=15)
        self.eq_kind_combo.pack(side='left',padx=3);self.eq_kind_combo.bind('<<ComboboxSelected>>',lambda e:self.eq_quick_apply())
        self.eq_on=tk.BooleanVar(value=True);self.eq_lock=tk.BooleanVar(value=False)
        ttk.Checkbutton(row,text=_('Вкл.'),variable=self.eq_on,command=self.eq_quick_apply).pack(side='left',padx=7)
        ttk.Checkbutton(row,text='Lock',variable=self.eq_lock,command=self.eq_quick_apply).pack(side='left',padx=5)
        ttk.Button(row,text=_('Подробнее…'),command=self.edit_bq,width=11).pack(side='right')
        ttk.Button(row,text='0 dB',command=self.eq_neutral,width=6).pack(side='right',padx=4)
        self.eq_f=tk.StringVar();self.eq_q=tk.StringVar();self.eq_gain=tk.StringVar()
        self.slider_vars={};self.sliders={};self.slider_entries={};self.slider_labels={}
        slab=ttk.Frame(p);slab.pack(fill='x',pady=2)
        for col,(key,label,var) in enumerate([('f','Частота',self.eq_f),('q','Ширина / Q',self.eq_q),('gain','Усиление',self.eq_gain)]):
            slab.columnconfigure(col,weight=1,uniform='slider')
            cell=ttk.Frame(slab,padding=(10,2));cell.grid(row=0,column=col,sticky='ew')
            labelw=ttk.Label(cell,text=_(label));labelw.pack(anchor='w');self.slider_labels[key]=labelw
            value=tk.DoubleVar(value=0);self.slider_vars[key]=value
            scale=ttk.Scale(cell,orient='horizontal',from_=0,to=1,variable=value,command=lambda v,k=key:self.slider_changed(k,v))
            scale.pack(fill='x',pady=4);self.sliders[key]=scale
            scale.bind('<ButtonPress-1>',self.slider_begin,add='+');scale.bind('<ButtonRelease-1>',self.slider_end,add='+')
            scale.bind('<KeyPress>',self.slider_begin,add='+');scale.bind('<KeyRelease>',self.slider_end,add='+')
            e=ttk.Entry(cell,textvariable=var,width=15,justify='center');e.pack(fill='x');self.slider_entries[key]=e
            e.bind('<Return>',lambda ev:self.eq_quick_apply());e.bind('<FocusOut>',lambda ev:self.eq_quick_apply())
        self.editor_note=ttk.Label(p,text=_('FIR не пересчитывается при ручной коррекции BQ.'),style='Small.TLabel',wraplength=1020);self.editor_note.pack(anchor='w',padx=10,pady=(7,0))

    def _all_bands_ui(self,p):
        controls=ttk.Frame(p);controls.pack(fill='x',pady=3)
        for text,cmd in [('Добавить',self.add_bq),('Дублировать',self.duplicate_bq),('Удалить',self.remove_bq),('↑',lambda:self.move_bq(-1)),('↓',lambda:self.move_bq(1)),('Отмена действия',self.undo),('Повтор действия',self.redo)]:
            ttk.Button(controls,text=_(text),command=cmd,width=3 if text in ('↑','↓') else 14).pack(side='left',padx=2)
        cols=('on','lock','name','type','freq','q','gain','bounds')
        frame=ttk.Frame(p);frame.pack(fill='both',expand=True)
        self.bqtree=ttk.Treeview(frame,columns=cols,show='headings',height=5,selectmode='browse')
        for c,t,w in zip(cols,['On','Lock','Секция','Тип','Hz','Q / S','dB','Диапазон авто, Hz'],[38,42,140,130,90,70,65,130]):
            self.bqtree.heading(c,text=_(t));self.bqtree.column(c,width=w,anchor='w' if c in ('name','type','bounds') else 'center',stretch=c in ('name','bounds'))
        self.bqtree.pack(side='left',fill='both',expand=True)
        sb=ttk.Scrollbar(frame,orient='vertical',command=self.bqtree.yview);sb.pack(side='right',fill='y');self.bqtree.configure(yscrollcommand=sb.set)
        self.bqtree.bind('<<TreeviewSelect>>',self.on_bq_select)
        self.bqtree.bind('<Double-1>',lambda e:self.edit_bq())
        self._bind_wheel_scroll(self.bqtree,self.bqtree)

    def _bq_values(self,b):
        values=list(super()._bq_values(b));values[3]=_(b.kind)+('*' if b.raw is not None else '')
        return values

    def sync_output_gain(self):
        if not hasattr(self,'output_gain_slider'):return
        m=self.session.model
        self._sync_controls=True
        try:
            if m is None:
                self.output_gain_value.set(0.0);self.output_gain_text.set('0.000')
                self.output_gain_slider.configure(state='disabled');self.output_gain_entry.configure(state='disabled')
            else:
                value=float(m.output_gain_db);self.output_gain_value.set(np.clip(value,-60,60));self.output_gain_text.set(f'{value:+.3f}')
                state='disabled' if self.busy else 'normal';self.output_gain_slider.configure(state=state);self.output_gain_entry.configure(state=state)
        finally:self._sync_controls=False

    def output_gain_begin(self,event=None):
        if self._sync_controls or self.busy or self.session.model is None:return
        self._gain_slider_active=True;self._gain_slider_saved=False

    def output_gain_end(self,event=None):
        self._gain_slider_active=False;self._gain_slider_saved=False;self.sync_output_gain();self.schedule_plot()

    def _set_output_gain(self,value,push=True):
        if self._sync_controls or self.busy or self.session.model is None:return
        value=float(np.clip(value,-60.,60.))
        if abs(value-self.session.model.output_gain_db)<1e-10:return
        if push:self.push_undo()
        self.session.model.output_gain_db=value;self.audio_render=None;self.player.stop();self.dirty=True;self._metrics_due=True
        self.output_gain_text.set(f'{value:+.3f}');self.schedule_plot()

    def output_gain_changed(self,value):
        if self._sync_controls or self.busy or self.session.model is None:return
        if not self._gain_slider_saved:self.push_undo();self._gain_slider_saved=True
        self._set_output_gain(float(value),push=False)
        if not self._gain_slider_active:self._gain_slider_saved=False

    def output_gain_apply(self):
        if self._sync_controls or self.busy or self.session.model is None:return
        try:self._set_output_gain(float(self.output_gain_text.get().replace(',','.')),push=True);self.sync_output_gain()
        except Exception as e:self.error(e);self.sync_output_gain()

    def output_gain_zero(self):
        if not self.guard_model():return
        self._set_output_gain(0.0,push=True);self.sync_output_gain()

    def _band_names(self):
        m=self.session.model
        return [f'{i+1:02d}  {b.name}'+('  [OFF]' if not b.enabled else '') for i,b in enumerate(m.sections)] if m else []

    def select_band_combo(self,event=None):
        i=self.band_selector.current()
        if i>=0 and self.bqtree.exists(str(i)):
            self.bqtree.selection_set(str(i));self.bqtree.see(str(i));self.sync_eq_quick();self.schedule_plot()

    def on_bq_select(self,event=None):
        self.sync_eq_quick();self.schedule_plot()

    def sync_eq_quick(self):
        self.sync_output_gain()
        if not hasattr(self,'bqtree'):return
        i=self.selected_bq();m=self.session.model
        names=self._band_names();self.band_selector.configure(values=names)
        if m is None or i is None or i>=len(m.sections):
            self._sync_controls=True
            self.band_choice.set(_('Нет секций BQ'))
            for v in (self.eq_f,self.eq_q,self.eq_gain):v.set('')
            for wid in list(self.sliders.values())+list(self.slider_entries.values()):wid.configure(state='disabled')
            self.eq_kind_combo.configure(state='disabled');self._sync_controls=False;return
        b=m.sections[i];self._sync_controls=True
        try:
            self.band_selector.current(i);self.eq_kind.set(b.kind)
            self.eq_f.set(f'{b.f:.3f}');self.eq_q.set(f'{b.q:.4f}');self.eq_gain.set(f'{b.gain:.3f}')
            self.eq_on.set(b.enabled);self.eq_lock.set(b.locked)
            self._eq_display={'f':self.eq_f.get(),'q':self.eq_q.get(),'gain':self.eq_gain.get()}
            self.eq_kind_combo.configure(state='readonly' if not self.busy else 'disabled')
            for key,var in self.slider_vars.items():
                var.set(self.param_to_slider(key,getattr(b,key),b))
                allowed=not self.busy and b.kind!='SOS' and (key!='gain' or b.kind in ('Peak','LowShelf','HighShelf'))
                self.sliders[key].configure(state='normal' if allowed else 'disabled')
                self.slider_entries[key].configure(state='normal' if allowed else 'disabled')
            self.slider_labels['q'].configure(text=_('Крутизна S' if 'Shelf' in b.kind else 'Ширина / Q'))
            msg=_('Прямой SOS: параметры частоты/Q не описывают точные коэффициенты. Используйте «Расширенные…».') if b.kind=='SOS' else _('Точная импортированная SOS. Изменение формы заменит её параметрической секцией.') if b.raw is not None else _('FIR не пересчитывается при ручной коррекции BQ.')
            if b.locked:msg+='  '+_('Lock защищает только от обучения. Ручная коррекция остаётся доступной.')
            self.editor_note.configure(text=msg)
        finally:self._sync_controls=False

    def slider_limits(self,key,b):
        if key=='f':return 10.,self.session.config.fs*.49
        if key=='q':return (.05,1.) if 'Shelf' in b.kind else (.08,24.)
        return -36.,36.

    def param_to_slider(self,key,val,b):
        lo,hi=self.slider_limits(key,b);v=float(np.clip(val,lo,hi))
        return (np.log(v/lo)/np.log(hi/lo)) if key in ('f','q') else (v-lo)/(hi-lo)

    def slider_to_param(self,key,val,b):
        lo,hi=self.slider_limits(key,b);t=float(np.clip(float(val),0,1))
        return lo*(hi/lo)**t if key in ('f','q') else lo+(hi-lo)*t

    def slider_begin(self,event=None):
        if not self._slider_active:
            self._slider_active=True;self._slider_saved=False
        self.eq_drag=None

    def slider_end(self,event=None):
        self._slider_active=False;self._slider_saved=False;self.sync_eq_quick();self.schedule_plot()

    def slider_changed(self,key,value):
        if self._sync_controls or self.busy or self.session.model is None:return
        i=self.selected_bq()
        if i is None:return
        b=self.session.model.sections[i]
        if b.kind=='SOS':return
        nb=copy.deepcopy(b);setattr(nb,key,self.slider_to_param(key,value,b));nb.raw=None
        try:
            active=nb.enabled;nb.enabled=True;nb.coefficients(self.session.config.fs);nb.enabled=active
        except Exception:return
        if abs(getattr(nb,key)-getattr(b,key))<1e-9:return
        if not self._slider_saved:self.push_undo();self._slider_saved=True
        self.session.model.sections[i]=nb;self.manual_bq_changed(i)
        if not self._slider_active:self._slider_saved=False

    def eq_quick_apply(self):
        if self._sync_controls or self.busy or self.session.model is None:return
        i=self.selected_bq()
        if i is None:return
        b=self.session.model.sections[i]
        try:
            nb=copy.deepcopy(b);nb.kind=self.eq_kind.get()
            if nb.kind!=b.kind:nb.control_role=''
            nb.enabled=self.eq_on.get();nb.locked=self.eq_lock.get()
            if nb.kind=='SOS' and b.kind!='SOS':self.edit_bq();self.sync_eq_quick();return
            if b.kind!='SOS':
                for key,var in [('f',self.eq_f),('q',self.eq_q),('gain',self.eq_gain)]:
                    if var.get()!=getattr(self,'_eq_display',{}).get(key):setattr(nb,key,float(var.get().replace(',','.')))
                if nb.kind in ('LowShelf','HighShelf'):nb.q=float(np.clip(nb.q,.05,1.))
            shape_changed=any(getattr(nb,k)!=getattr(b,k) for k in ('kind','f','q','gain'))
            if shape_changed:nb.raw=None
            on=nb.enabled;nb.enabled=True;nb.coefficients(self.session.config.fs);nb.enabled=on
            if nb.to_dict()==b.to_dict():return
            self.push_undo();self.session.model.sections[i]=nb;self.manual_bq_changed(i)
        except Exception as e:self.error(e);self.sync_eq_quick()

    def duplicate_bq(self):
        if not self.guard_model():return
        i=self.selected_bq()
        if i is None:return
        if len(self.session.model.sections)>=32:self.error(ValueError(_('Максимум 32 секции.')));return
        self.push_undo();b=copy.deepcopy(self.session.model.sections[i]);b.name+=' (copy)'
        b.control_role=''  # A duplicated correction does not own a second knob.
        self.session.model.sections.insert(i+1,b);self.changed();self.bqtree.selection_set(str(i+1))

    def manual_bq_changed(self,i=None,refresh_tree=True):
        self.audio_render=None;self.player.stop();self.dirty=True;self._metrics_due=True
        if refresh_tree:
            if i is None:self.refresh_bq()
            else:self._update_bq_row(i)
        self.sync_eq_quick();self.schedule_plot()

    def draw_eq_editor(self):
        # Retained for plugins/tests that used the 0.2 editor. There is only one graph.
        self.schedule_plot()

    def schedule_plot(self):
        if self.redraw_id:
            try:self.after_cancel(self.redraw_id)
            except tk.TclError:pass
        self.redraw_id=self.after(35 if self.eq_drag or self._slider_active else 110,self.redraw)

    def _can_edit(self):
        return (self.edit_enabled.get() and not self.busy and self.session.model is not None
                and self.plotvar.get() in EDIT_PLOTS and not self.nav.mode)

    def _nearest_eq_handle(self,event,max_px=18):
        if not self._can_edit() or event.inaxes not in (self.ax,self.band_ax) or not self.eq_handle_xy:return None
        if event.x is None or event.y is None:return None
        best=(1e9,None)
        for i,(x,y) in enumerate(self.eq_handle_xy):
            px=self.ax.transData.transform((x,y));d=float(np.hypot(px[0]-event.x,px[1]-event.y))
            if d<best[0]:best=(d,i)
        return best[1] if best[0]<=max_px else None

    def _event_data(self,event):
        if event.x is None or event.y is None:return None,None
        try:return self.ax.transData.inverted().transform((event.x,event.y))
        except Exception:return None,None

    def eq_press(self,event):
        if not self._can_edit():return
        i=self._nearest_eq_handle(event)
        if i is None:return
        self.bqtree.selection_set(str(i));self.bqtree.see(str(i));self.sync_eq_quick()
        if event.button==3:
            menu=tk.Menu(self,tearoff=False)
            for text,cmd in [('Bypass / Enable',self.toggle_bq),('Lock / Unlock',self.lock_bq),('0 dB',self.eq_neutral),('Расширенные…',self.edit_bq)]:menu.add_command(label=_(text),command=cmd)
            theme_widgets(menu,self.colors);ge=getattr(event,'guiEvent',None)
            if ge is not None:
                try:menu.tk_popup(ge.x_root,ge.y_root)
                finally:menu.grab_release()
            return
        if event.button!=1:return
        if event.dblclick:self.toggle_bq();return
        b=self.session.model.sections[i]
        if b.kind=='SOS':self.status.set(_('Прямой SOS редактируется через Advanced…'));return
        x,y=self._event_data(event)
        if x is None:return
        self.eq_drag={'i':i,'f':b.f,'g':b.gain,'x':max(x,1e-6),'y':y,'pushed':False}
        self._gesture_limits=(self.ax.get_xlim(),self.ax.get_ylim())

    def eq_motion(self,event):
        if not self.eq_drag or not self._can_edit() or event.inaxes not in (self.ax,self.band_ax):return
        x,y=self._event_data(event)
        if x is None or not np.isfinite(x) or x<=0:return
        i=self.eq_drag['i'];b=self.session.model.sections[i];nb=copy.deepcopy(b)
        factor=.18 if 'shift' in str(getattr(event,'key','')).lower() else 1.
        nb.f=float(np.clip(self.eq_drag['f']*(x/self.eq_drag['x'])**factor,10.,self.session.config.fs*.49))
        if nb.kind in ('Peak','LowShelf','HighShelf'):
            sensitivity=2. if 'Shelf' in nb.kind else 1.
            nb.gain=float(np.clip(self.eq_drag['g']+(y-self.eq_drag['y'])*factor*sensitivity,-36,36))
        nb.raw=None
        try:
            on=nb.enabled;nb.enabled=True;nb.coefficients(self.session.config.fs);nb.enabled=on
        except Exception:return
        if nb.to_dict()==b.to_dict():return
        if not self.eq_drag['pushed']:self.push_undo();self.eq_drag['pushed']=True
        self.session.model.sections[i]=nb;self.manual_bq_changed(i)

    def eq_release(self,event):
        if self.eq_drag:self.eq_drag=None;self.sync_eq_quick();self.schedule_plot()

    def eq_scroll(self,event):
        if not self._can_edit() or event.inaxes not in (self.ax,self.band_ax):return
        i=self._nearest_eq_handle(event,24)
        if i is None:i=self.selected_bq()
        if i is None:return
        b=self.session.model.sections[i]
        if b.kind=='SOS':return
        now=time.monotonic()
        if now-self.eq_last_wheel>.45 or self._wheel_band!=i:self.push_undo()
        self.eq_last_wheel=now;self._wheel_band=i
        factor=(1.025 if 'shift' in str(getattr(event,'key','')).lower() else 1.12)**float(event.step)
        lo,hi=self.slider_limits('q',b);b.q=float(np.clip(b.q*factor,lo,hi));b.raw=None
        self.bqtree.selection_set(str(i));self.manual_bq_changed(i)

    def redraw(self):
        self.redraw_id=None
        if not hasattr(self,'ax'):return
        old_limits=(self.ax.get_xlim(),self.ax.get_ylim()) if self._view_locked else None
        if self.band_ax is not None:
            self.band_ax.remove();self.band_ax=None
        self.ax.clear();self.eq_handle_xy=[]
        c=self.colors;ax=self.ax
        self.plot_combo.configure(values=[_(v) for v in (PLOTS if self.session.target is not None else [PLOTS[0]])])
        if self.session.model is None:
            ax.text(.5,.5,_('Загрузите IR WAV или откройте проект'),ha='center',va='center',transform=ax.transAxes)
            ax.set_axis_off();theme_axes(self.figure,ax,c);self.canvas.draw_idle();self.sync_eq_quick();return
        if self.session.target is None:
            m=self.session.model;f=frequency_grid(m.fs,3000);H=m.response(f)
            self._sync_figure_size();ax.set_axis_on()
            self._edit_trace=db(H)
            ax.semilogx(f,self._edit_trace,color=c['model'],label=_('Модель'))
            ax.set(xlabel=_('Частота, Hz'),ylabel=_('АЧХ, dB'),xlim=(float(self.flo.get()),min(float(self.fhi.get()),m.fs*.499)))
            ax.set_title(_('Model only — attach reference WAV to train'),fontsize=10,loc='left')
            if self.show_bands.get():self._draw_band_curves(ax,f,m.fs)
            if self._can_edit():self._draw_handles(f,self._edit_trace)
            if old_limits:ax.set_xlim(old_limits[0]);ax.set_ylim(old_limits[1])
            self.metrics_label.configure(text=_('No reference: comparison metrics and training are unavailable.'))
            theme_axes(self.figure,ax,c);self.canvas.draw_idle();self.sync_eq_quick();return
        try:
            m=self.training_preview if self.training_preview is not None else self.session.model
            fs=m.fs;f,T=self.target_response();H=m.response(f)
            self._sync_figure_size()
            mode=self.plotvar.get();flo=max(1,float(self.flo.get()));fhi=min(float(self.fhi.get()),fs*.499)
            if fhi<=flo:raise ValueError(_('Максимальная частота должна быть выше минимальной.'))
            visible=(f>=flo)&(f<=fhi)
            def smooth(y):
                sm=self.smoothing.get()
                if sm=='Без':return y
                sigma=(np.log(2)/float(sm.split('/')[1]))/(np.log(f[1]/f[0])*2.355)
                return ndimage.gaussian_filter1d(y,sigma,mode='nearest')
            ax.set_axis_on();self._edit_trace=None
            series=[(_('Эталон'),T,c['ref'],'-',1.9),(_('Модель'),H,c['model'],'-',2.0)]
            if self.showraw.get():
                if 'raw' not in self.target_cache:
                    source=self.session.source
                    if source.ndim==2:
                        ch=self.session.config.channel;source=source.mean(axis=1) if ch==-1 else source[:,ch]
                    raw=fir_response(source,f,self.session.source_fs);raw[f>self.session.source_fs/2]=np.nan;self.target_cache['raw']=raw
                series.append((_('Raw WAV, без норм.'),self.target_cache['raw'],c['bands'][2],':',1.0))
            if self.showpre.get():
                if 'pre' not in self.target_cache:self.target_cache['pre']=fir_response(self.session.before_mpt,f,fs)
                series.append((_('До MPT'),self.target_cache['pre'],c['bands'][3],':',1.1))
            if self.showquant.get():series.append((_('Модель Q15/float32'),m.response(f,True),c['bands'][4],'--',1.0))
            if self.pure.get()!='Нет':
                n=int(self.pure.get());key=f'pure{n}'
                if key not in self.target_cache:self.target_cache[key]=fir_response(self.session.target[:n],f,fs)
                series.append((f'Pure {n}',self.target_cache[key],c['bands'][2],'--',1.15))
            for j,i in enumerate(self.stree.selection()[:4]):
                snap=self.session.snapshots[int(i)]
                series.append((snap.name,snap.response(f),c['bands'][(j+3)%len(c['bands'])],'-',1.0))
            if mode==PLOTS[5]:
                ref=self.session.target;render=m.render();n=min(len(ref),int(fs*.06));k=min(len(render),int(fs*.06))
                ax.plot(np.arange(n)/fs*1000,ref[:n],color=c['ref'],label=_('Эталон'))
                ax.plot(np.arange(k)/fs*1000,render[:k],color=c['model'],label=_('Модель'))
                ax.set(xlabel=_('Время, ms'),ylabel=_('Амплитуда'),xlim=(0,50))
            elif mode==PLOTS[6]:
                F=fir_response(m.fir,f,fs) if m.fir_enabled else np.ones(len(f),complex)
                need=db(T)-db(F)-m.output_gain_db
                total=sos_response(sos_array(m.sections,fs),f,fs)
                ax.semilogx(f,smooth(need),color=c['target'],linestyle='--',linewidth=1.3,label=_('Требуемая коррекция BQ'))
                ax.semilogx(f,smooth(db(total)),color=c['model'],linewidth=2,label=_('Каскад BQ'))
                self._edit_trace=db(total)
                ax.set(xlabel=_('Частота, Hz'),ylabel='BQ gain, dB',xlim=(flo,fhi))
                self._set_display_ylim([need,db(total)],visible,mode)
                if self.show_bands.get():self._draw_band_curves(ax,f,fs)
            else:
                curves=[]
                for label,response,color,ls,lw in series:
                    if mode==PLOTS[0]:y=smooth(db(response));yl=_('АЧХ, dB')
                    elif mode==PLOTS[1]:y=smooth(db(response)-db(T));yl=_('ΔАЧХ, dB')
                    elif mode==PLOTS[2]:y=np.unwrap(np.angle(response))*180/np.pi;yl=_('Фаза, °')
                    elif mode==PLOTS[3]:
                        y=np.angle(response*np.conj(T))*180/np.pi;yl=_('ΔФЧХ, °')
                        if self.detrend.get():
                            y=np.unwrap(np.angle(response*np.conj(T)))*180/np.pi;mask=(f>=max(80,flo))&(f<=min(8000,fhi))
                            if np.count_nonzero(mask)>2:
                                basis=np.c_[np.ones(len(f)),f/8000];co=np.linalg.lstsq(basis[mask],y[mask],rcond=None)[0];y-=basis@co
                            yl=_('Detrended Δφ, ° — ТОЛЬКО ДИАГНОСТИКА')
                    elif mode==PLOTS[4]:
                        y=-np.gradient(np.unwrap(np.angle(response)),2*np.pi*f)*1000;yl=_('Групповая задержка, ms')
                        valid=abs(response)>np.nanmax(abs(response))*1e-4;y=np.where(valid,y,np.nan)
                    else:
                        if label==_('Эталон'):continue
                        y=db(response-T)-20*np.log10(max(np.max(abs(T)),1e-30));yl=_('|Hmodel − Href|, dB относительно max |Href|')
                    ax.semilogx(f,y,color=color,linestyle=ls,linewidth=lw,label=label);curves.append(y)
                ax.set(xlabel=_('Частота, Hz'),ylabel=yl,xlim=(flo,fhi))
                if mode in (PLOTS[0],PLOTS[1]):
                    self._edit_trace=smooth(db(H) if mode==PLOTS[0] else db(H)-db(T));self._set_display_ylim(curves,visible,mode)
                if mode in (PLOTS[1],PLOTS[3]):ax.axhline(0,color=c['muted'],alpha=.6,linewidth=.65,linestyle='--')
                if (self.show_bands.get() or self.show_bq_sum.get()) and mode in (PLOTS[0],PLOTS[1]):
                    self.band_ax=ax.twinx();self.band_ax.patch.set_visible(False);self.band_ax.set_navigate(False)
                    self.band_ax.set_zorder(ax.get_zorder()-1)
                    ax.set_zorder(self.band_ax.get_zorder()+1);ax.patch.set_visible(False)
                    if self.show_bands.get():self._draw_band_curves(self.band_ax,f,fs)
                    if self.show_bq_sum.get():
                        total=db(sos_response(sos_array(m.sections,fs),f,fs))
                        self.band_ax.semilogx(f,total,color=c['sum'],linewidth=1.4,alpha=.75,label=_('Σ BQ'))
                        ax.plot([],[],color=c['sum'],linewidth=1.4,label=_('Σ BQ'))
                    self.band_ax.set_ylim(-36,36);self.band_ax.set_ylabel('BQ · dB',color=c['muted'],fontsize=9)
                    self.band_ax.tick_params(colors=c['muted'],labelsize=8)
                    for spine in self.band_ax.spines.values():spine.set_color(c['border'])
                else:ax.patch.set_visible(True)
            if old_limits:
                ax.set_xlim(old_limits[0]);ax.set_ylim(old_limits[1])
            if self.eq_drag and hasattr(self,'_gesture_limits'):
                ax.set_xlim(self._gesture_limits[0]);ax.set_ylim(self._gesture_limits[1])
            if not self.busy and self.edit_enabled.get() and mode in EDIT_PLOTS and self._edit_trace is not None:
                self._draw_handles(f,self._edit_trace)
            selected=self.selected_bq()
            note=_('Точка: F/G · Колесо: Q/S · Shift: точно') if self._can_edit() else _('Точки доступны в АЧХ, ΔАЧХ и BQ. На остальных графиках используйте нижний редактор.') if self.edit_enabled.get() else _('Переключите «Редактировать», чтобы менять BQ на графике.')
            self.plot_hint.configure(text=note)
            title=_(mode)+('  ·  FIR BYPASS' if not m.fir_enabled else '')
            ax.set_title(title,fontsize=11,loc='left',pad=12)
            if ax.get_legend_handles_labels()[0]:ax.legend(loc='upper right',fontsize=8,ncol=2,framealpha=.85)
            theme_axes(self.figure,ax,c);self.canvas.draw_idle()
            if not self.eq_drag and not self._slider_active:self._update_metrics(f,T,H,m)
        except Exception as e:
            self.status.set(_('График: ')+str(e));self.log(_('Ошибка графика: ')+str(e))

    def _sync_figure_size(self):
        # Tk may update the device-pixel ratio after the first Configure event.
        # Match renderer pixels to the actual Tk photo: avoids clipping axes on HiDPI.
        widget=self.canvas.get_tk_widget()
        w,h=widget.winfo_width(),widget.winfo_height()
        if w>10 and h>10:
            fw,fh=self.figure.bbox.width,self.figure.bbox.height
            if abs(fw-w)>.5 or abs(fh-h)>.5:
                self.figure.set_size_inches(w/self.figure.dpi,h/self.figure.dpi,forward=False)

    def _set_display_ylim(self,curves,mask,mode):
        # A percentile view keeps noise-floor notches from crushing the plot.
        # Curves are not altered. Fit limits include the full range for error plots.
        vals=np.concatenate([np.asarray(y)[mask] for y in curves]);vals=vals[np.isfinite(vals)]
        if not len(vals):return
        if mode==PLOTS[0]:
            low=max(float(np.min(vals))-3,float(np.max(vals))-78);high=float(np.max(vals))+4
        elif mode==PLOTS[1]:
            s=max(3.,float(np.max(np.abs(vals)))*1.12);low,high=-s,s
        else:
            low=max(-90.,float(np.percentile(vals,1))-4);high=min(60.,float(np.percentile(vals,99))+4)
        if high-low<6:low-=3;high+=3
        self.ax.set_ylim(low,high)

    def _draw_band_curves(self,axes,f,fs):
        selected=self.selected_bq()
        model=self.training_preview if self.training_preview is not None else self.session.model
        for i,b in enumerate(model.sections):
            color=self.colors['bands'][i%len(self.colors['bands'])]
            response=db(sos_response([b.coefficients(fs)],f,fs))
            axes.semilogx(f,response,color=color,linewidth=1.5 if i==selected else .85,
                         alpha=(.75 if i==selected else .36) if b.enabled else .2,
                         linestyle='-' if b.enabled else ':',gid='individual-bq')

    def _draw_handles(self,f,trace):
        self.eq_handle_xy=[];selected=self.selected_bq()
        for i,b in enumerate(self.session.model.sections):
            y=float(np.interp(b.f,f,trace));self.eq_handle_xy.append((b.f,y))
            if not self.ax.get_xlim()[0]<=b.f<=self.ax.get_xlim()[1]:continue
            color=self.colors['bands'][i%len(self.colors['bands'])]
            self.ax.scatter([b.f],[y],s=92 if i==selected else 58,facecolors=color if b.enabled else self.colors['panel'],
                            edgecolors=self.colors['fg'] if i==selected else color,linewidths=1.6,zorder=10,gid='bq-handle')
            text=self.ax.annotate(str(i+1),(b.f,y),xytext=(0,10),textcoords='offset points',ha='center',fontsize=8,color=color,zorder=11)
            text.set_gid('band-text')

    def _update_metrics(self,f,T,H,m):
        rows=response_metrics(T,H,f,m.fs);diag=phase_diagnostics(T,H,f,m.fs)
        text=_('Диапазон       RMS dB   Max dB   P95 dB   Фаза RMS °')+'\n'
        for r in rows:
            text+=f'{r["band"]:12s} {r["mag_rms_db"]:8.3f} {r["mag_max_db"]:8.3f} {r["mag_p95_db"]:8.3f} {r["phase_rms_deg"]:10.2f}\n'
        text+=_tf('Диагностический detrend: offset {0:+.2f}°, delay {1:+.4f} samples; ripple {2:.2f}°',diag['offset_deg'],diag['delay_samples'],diag['ripple_deg'])+'\n'
        pole=sos_stability(sos_array(m.sections,m.fs,True));nom=(len(m.fir) if m.fir_enabled else 0)+5*len(m.sections)+(1 if abs(m.output_gain_db)>1e-12 else 0)
        firtxt=f'FIR {len(m.fir)}' if m.fir_enabled else f'FIR BYPASS ({len(m.fir)} taps)'
        text+=f'{firtxt}; BQ {len(m.sections)}; Overall Gain {m.output_gain_db:+.3f} dB; pole radius float32 {pole:.7f}; '+_tf('~{0} умножений/sample (НЕ DSP %).',nom)
        self.metrics_label.configure(text=text)

    def _capture_ui_state(self):
        scalar=['taps','count','preset','mode','objective','fit_gain','profile','greedy','fir_enabled','plotvar','showraw','showpre','showquant','pure',
                'flo','fhi','smoothing','detrend','match_rms','preview_db','edit_enabled','show_bands','show_bq_sum']
        return dict(vars={k:getattr(self,k).get() for k in scalar},prep={k:v.get() for k,v in self.pvars.items()},
                    fit={k:v.get() for k,v in self.fitvars.items()},options=self.options.index(self.options.select()),
                    tab=self.tabs.index(self.tabs.select()),selected=self.selected_bq(),snapshots=self.stree.selection(),
                    tools=self._tools_visible,log=self.logtext.get('1.0','end-1c'),dirty=self.dirty,
                    sashes=(self.mainpane.sashpos(0) if self._tools_visible else 300,self.split.sashpos(0)),
                    zoom=self.zoom_panel.capture(),library=self.library_panel.capture(),
                    catalog=self._catalog_active,trainer_sash=self._trainer_sash)

    def _save_settings_quietly(self):
        try:save_preferences(self.prefs)
        except OSError as e:
            if hasattr(self,'status'):self.status.set(_('Не удалось сохранить настройки: ')+str(e))

    def apply_preferences(self,language,theme):
        if not self.guard(False):return False
        if language not in ('ru','en') or theme not in ('dark','light'):raise ValueError('Invalid language/theme')
        state=self._capture_ui_state()
        self.eq_drag=None;self.player.stop()
        for attr in ('_idle_draw_id','_event_loop_id'):
            token=getattr(self.canvas,attr,None)
            if token:
                try:self.canvas.get_tk_widget().after_cancel(token)
                except tk.TclError:pass
                setattr(self.canvas,attr,None)
        if self.redraw_id:
            self.after_cancel(self.redraw_id);self.redraw_id=None
        self.prefs.language=language;self.prefs.theme=theme
        self.prefs.edit_enabled=self.edit_enabled.get();self.prefs.show_bands=self.show_bands.get();self.prefs.show_bq_sum=self.show_bq_sum.get()
        set_language(language)
        for child in self.winfo_children():child.destroy()
        self.configure(menu='');self._view_locked=False
        self._make_ui()
        for k,v in state['vars'].items():getattr(self,k).set(v)
        for k,v in state['prep'].items():self.pvars[k].set(v)
        for k,v in state['fit'].items():self.fitvars[k].set(v)
        self.zoom_panel.restore(state['zoom'])
        self.library_panel.restore(state['library'])
        self.options.select(state['options']);self.tabs.select(state['tab'])
        self._catalog_active=state['catalog'];self._trainer_sash=state['trainer_sash']
        self.refresh_bq();self.refresh_snapshots()
        i=state['selected']
        if i is not None and self.bqtree.exists(str(i)):self.bqtree.selection_set(str(i))
        valid=[i for i in state['snapshots'] if self.stree.exists(i)]
        if valid:self.stree.selection_set(valid)
        self.logtext.insert('end','\n'.join(_(line) for line in state['log'].split('\n')));self.dirty=state['dirty']
        if self.session.source is not None:self.file_label.configure(text=f'{self.session.source_name} | {self.session.config.fs} Hz')
        if self.audio_file:self.di_label.configure(text=_('Вход: ')+__import__('pathlib').Path(self.audio_file).name)
        if not state['tools']:self.toggle_tools()
        self.after_idle(lambda:self._restore_sashes(state['sashes']))
        apply_theme(self,theme);self.sync_eq_quick();self.redraw();self._save_settings_quietly()
        self.status.set(_('Настройки сохранены.'));return True

    def _restore_sashes(self,values):
        try:
            if self._tools_visible:self.mainpane.sashpos(0,values[0])
            self.split.sashpos(0,values[1])
        except tk.TclError:pass

    def open_settings(self):
        """Compatibility entry point: preferences now live in the header."""
        self.language_selector.focus_set()

    def show_help(self):
        messagebox.showinfo(_('Краткая инструкция'),_('HELP_030'),parent=self)

    def close(self):
        self._save_settings_quietly()
        super().close()

    def destroy(self):
        # Cancel Tk timers before deleting registered callbacks (including Matplotlib idle draws).
        if getattr(self,'_destroying',False):return
        self._destroying=True
        try:
            # Cancel a Python timer through its registering widget. Deleting a
            # Canvas command through the root leaves a stale child command list.
            owners={}
            def collect(widget):
                for command in getattr(widget,'_tclCommands',None) or []:owners[command]=widget
                for child in widget.winfo_children():collect(child)
            collect(self)
            for token in self.tk.call('after','info'):
                try:
                    script=self.tk.call('after','info',token)[0]
                    owner=owners.get(str(script))
                    if owner:owner.after_cancel(token)
                    else:self.tk.call('after','cancel',token)
                except tk.TclError:pass
        except tk.TclError:pass
        super().destroy()
