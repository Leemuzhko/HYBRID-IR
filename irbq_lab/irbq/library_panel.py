"""Processed IR library, sharing the existing Trainer and bank exporter."""
from __future__ import annotations
import copy
import re
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .i18n import tr
from .authoring import default_library_path, scan_library, library_session
from .zoom_bank import Slot


class LibraryPanel(ttk.Frame):
    def __init__(self,app,parent):
        super().__init__(parent,padding=8)
        self.app=app;self.entries=[];self.loaded_folder=None
        self.columnconfigure(0,weight=1);self.rowconfigure(2,weight=1)
        self.folder=tk.StringVar(value=app.prefs.library_folder or str(default_library_path()))
        head=ttk.Frame(self);head.grid(row=0,column=0,sticky='ew');head.columnconfigure(1,weight=1)
        ttk.Label(head,text=tr('Library folder:')).grid(row=0,column=0,padx=(0,8))
        ttk.Entry(head,textvariable=self.folder).grid(row=0,column=1,sticky='ew')
        ttk.Button(head,text='…',width=3,style='Compact.TButton',command=self.browse).grid(row=0,column=2,padx=4)
        ttk.Button(head,text=tr('Refresh'),style='Compact.TButton',command=lambda:self.app.zoom_panel.guarded(self.refresh)).grid(row=0,column=3)
        filters=ttk.Frame(self);filters.grid(row=1,column=0,sticky='ew',pady=4)
        self.query=tk.StringVar();self.kind=tk.StringVar(value='All');self.taps=tk.StringVar();self.bqs=tk.StringVar()
        for col,(label,var,values) in enumerate([('Search',self.query,None),('Type',self.kind,['All','FIR','BQ','Hybrid']),
                                               ('Max FIR',self.taps,None),('Max BQ',self.bqs,None)]):
            ttk.Label(filters,text=tr(label)).grid(row=0,column=col*2,padx=(0,4))
            widget=(ttk.Combobox(filters,textvariable=var,values=values,state='readonly',width=9) if values
                    else ttk.Entry(filters,textvariable=var,width=22 if col==0 else 7))
            widget.grid(row=0,column=col*2+1,padx=(0,12));var.trace_add('write',lambda *_:self.filter())
        body=ttk.Frame(self);body.grid(row=2,column=0,sticky='nsew');body.columnconfigure(0,weight=1);body.rowconfigure(0,weight=1)
        self.tree=ttk.Treeview(body,columns=('name','type','fir','bq','gain','reference'),show='headings',selectmode='extended',height=14)
        for key,label,width in [('name','Project',240),('type','Type',80),('fir','FIR taps',80),('bq','BQ total',80),('gain','Gain dB',80),('reference','Reference',110)]:
            self.tree.heading(key,text=tr(label));self.tree.column(key,width=width,minwidth=50,anchor='e' if key in ('fir','bq','gain') else 'w')
        self.tree.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(body,orient='vertical',command=self.tree.yview);scroll.grid(row=0,column=1,sticky='ns')
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<Double-1>',lambda e:self.app.zoom_panel.guarded(self.edit))
        actions=ttk.Frame(self);actions.grid(row=3,column=0,sticky='ew',pady=(4,0))
        for col,(label,fn) in enumerate([('Add selected to bank',self.add_selected),('Edit in Trainer',self.edit),('Save current to library',self.save_current)]):
            ttk.Button(actions,text=tr(label),style='Compact.TButton',command=lambda f=fn:self.app.zoom_panel.guarded(f)).grid(row=0,column=col,padx=(0,4),pady=2,sticky='ew')
        more=ttk.Menubutton(actions,text=tr('Import'),style='Compact.TMenubutton');more.grid(row=0,column=3)
        menu=tk.Menu(more,tearoff=False);more.configure(menu=menu)
        for label,fn in [('Import projects / models',self.import_files),('Attach reference WAV',app.attach_reference)]:
            menu.add_command(label=tr(label),command=lambda f=fn:self.app.zoom_panel.guarded(f))
        self.note=tk.StringVar(value=tr('Projects retain references. Model JSON contains coefficients only.'))
        self.note.trace_add('write',lambda *_:app.status.set(self.note.get()) if hasattr(app,'status') else None)

    def capture(self):
        return dict(folder=self.folder.get(),query=self.query.get(),kind=self.kind.get(),taps=self.taps.get(),bqs=self.bqs.get(),
                    entries=self.entries,loaded=self.loaded_folder,selected=self.tree.selection())

    def restore(self,state):
        for name in ('folder','query','kind','taps','bqs'):getattr(self,name).set(state[name])
        self.entries=state['entries'];self.loaded_folder=state['loaded'];self.filter()
        self.tree.selection_set([i for i in state['selected'] if self.tree.exists(i)])

    def browse(self):
        path=filedialog.askdirectory(parent=self,initialdir=self.folder.get())
        if path:self.folder.set(path);self.refresh()

    def ensure_loaded(self):
        if not self.app.busy and self.loaded_folder!=self.folder.get():self.refresh()

    def refresh(self):
        if not self.app.guard(False):return
        folder=Path(self.folder.get()).expanduser()
        def check_cancel():
            from .trainer import Cancelled
            if self.app.cancel_event.is_set():raise Cancelled()
        def task():
            check_cancel()
            folder.mkdir(parents=True,exist_ok=True)
            return scan_library(folder,check_cancel)
        def done(result):
            self.entries,errors=result;self.loaded_folder=str(folder)
            self.app.prefs.library_folder=str(folder);self.app._save_settings_quietly();self.filter()
            self.note.set(tr('{count} projects; {errors} unreadable files').format(count=len(self.entries),errors=len(errors)))
            for path,error in errors:self.app.log(str(path)+': '+error)
        self.app.run_job(task,done,tr('Reading library'))

    def filter(self):
        from .zoom_rbj_bank import bq_count
        selected=set(self.tree.selection());self.tree.delete(*self.tree.get_children())
        try:
            limits=[int(v.get()) if v.get().strip() else None for v in (self.taps,self.bqs)]
            if any(n is not None and n<0 for n in limits):raise ValueError()
        except ValueError:
            self.note.set(tr('Filter limits must be non-negative integers'));return
        for i,entry in enumerate(self.entries):
            model=entry.session.model;taps=len(model.fir) if model.fir_enabled else 0;bq=bq_count(model)
            if self.query.get().casefold() not in entry.path.stem.casefold():continue
            if self.kind.get()!='All' and entry.kind!=self.kind.get():continue
            if limits[0] is not None and taps>limits[0] or limits[1] is not None and bq>limits[1]:continue
            self.tree.insert('', 'end',iid=str(i),values=(entry.path.stem,entry.kind,taps,bq,f'{model.output_gain_db:+.2f}',
                tr('Available' if entry.session.target is not None else 'Model only')))
        self.tree.selection_set([i for i in selected if self.tree.exists(i)])

    def selected(self):
        return [self.entries[int(i)] for i in self.tree.selection()]

    def add_selected(self):
        entries=self.selected();panel=self.app.zoom_panel
        if not entries:return
        if len(panel.project.slots)+len(entries)>8:raise ValueError(tr('A bank supports at most 8 slots'))
        from .zoom_bank import validate_model
        used={slot.label for slot in panel.project.slots};slots=[]
        for entry in entries:
            model=panel.prepare_roles(entry.session.model)
            if model is None:return  # Entire batch remains inert on cancellation.
            validate_model(model)
            base=re.sub('[^A-Z0-9]','',entry.path.stem.upper())[:5] or 'IR'
            if base=='OFF':base='IR'
            label=base;n=1
            while label in used:
                suffix=str(n);label=base[:5-len(suffix)]+suffix;n+=1
            used.add(label)
            session=copy.deepcopy(entry.session);session.model=model.clone()
            slots.append(Slot(label,model,session))
        panel.project.slots.extend(slots);panel.mark_dirty();panel.refresh()
        self.app.tabs.select(panel)

    def edit(self):
        entries=self.selected()
        if len(entries)!=1:raise ValueError(tr('Select one project to edit'))
        if not self.app.confirm_session():return
        entry=entries[0]
        self.app.install_session(copy.deepcopy(entry.session),entry.path if entry.path.suffix.lower()=='.irbq' else None)
        self.app.tabs.select(self.app.tabs.tabs()[0])

    def save_current(self):
        if not self.app.guard_model():return
        selected=self.selected()
        basename=selected[0].path.with_suffix('.irbq').name if len(selected)==1 else 'Cabinet.irbq'
        path=filedialog.asksaveasfilename(parent=self,initialdir=self.folder.get(),initialfile=basename,
            defaultextension='.irbq',filetypes=[('IRBQ project','*.irbq')],confirmoverwrite=False)
        if not path:return
        if Path(path).exists() and not messagebox.askyesno(tr('Replace library project?'),str(path),parent=self):return
        self.app.session.save(path);self.refresh()

    def import_files(self):
        paths=filedialog.askopenfilenames(parent=self,filetypes=[('Projects / models','*.irbq *.json')])
        if not paths:return
        # Validate the full selection before writing; collisions always require consent.
        prepared=[];destinations=set();folder=Path(self.folder.get())
        for path in paths:
            session=library_session(path);dest=folder/(Path(path).stem+'.irbq')
            if dest in destinations:raise ValueError(tr('Import filenames collide; import them separately'))
            if dest.exists() and not messagebox.askyesno(tr('Replace library project?'),str(dest),parent=self):return
            destinations.add(dest);prepared.append((dest,session))
        for dest,session in prepared:session.save(dest)
        self.refresh()
