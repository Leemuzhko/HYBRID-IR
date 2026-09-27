"""A bank tab in the existing Trainer, not a replacement application."""
import copy
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import numpy as np
from .dsp import Model
from .project import Session
from .zoom_bank import BankProject, Slot, pack_bank, build_project, catalog_entries, suggest_free_id, import_irbq_package


class ZoomPanel(ttk.Frame):
    def __init__(self, app, parent):
        super().__init__(parent, padding=8)
        self.app = app
        self.project = BankProject()
        self.dirty = False
        self.variables = {}
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text='Zoom bank · OFF is automatic · hardware slot limit not established',
                  style='Small.TLabel').grid(row=0, column=0, columnspan=2, sticky='w', pady=(0,8))
        left=ttk.Frame(self);left.grid(row=1,column=0,sticky='nsew',padx=(0,12))
        left.columnconfigure(0,weight=1);left.rowconfigure(0,weight=1)
        self.tree=ttk.Treeview(left,columns=('label','fir','bq','gain'),show='headings',height=5,selectmode='browse')
        for key,label,width in [('label','IR label',110),('fir','FIR taps',70),('bq','BQ total',70),('gain','Gain dB',70)]:
            self.tree.heading(key,text=label);self.tree.column(key,width=width,anchor='w' if key=='label' else 'e')
        self.tree.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(left,orient='vertical',command=self.tree.yview)
        scroll.grid(row=0,column=1,sticky='ns');self.tree.configure(yscrollcommand=scroll.set)
        actions=ttk.Frame(left);actions.grid(row=1,column=0,columnspan=2,sticky='w',pady=(8,0))
        for index,(text,command) in enumerate([('Current model',self.current),('Import JSON',self.import_json),('Import WAV',self.import_wav),
                             ('Rename',self.rename),('↑',lambda:self.move(-1)),('↓',lambda:self.move(1)),('Remove',self.remove)]):
            ttk.Button(actions,text=text,command=lambda fn=command:self.guarded(fn)).grid(row=index//4,column=index%4,sticky='ew',padx=(0,4),pady=2)
        settings=ttk.Frame(self);settings.grid(row=1,column=1,sticky='nsew')
        settings.columnconfigure(1,weight=1)
        for row,(key,label) in enumerate([('name','Display name'),('filename','ZDL basename'),('fxid','Effect ID'),
                                           ('image','Card PNG'),('patched_folder','ZEM custom ZDL folder')]):
            ttk.Label(settings,text=label).grid(row=row,column=0,sticky='w',padx=(0,8),pady=2)
            v=tk.StringVar(value=str(getattr(self.project,key)));self.variables[key]=v
            v.trace_add('write',lambda *_:self.mark_dirty())
            ttk.Entry(settings,textvariable=v).grid(row=row,column=1,sticky='ew',pady=2)
            if key in ('image','stock_folder','patched_folder'):
                ttk.Button(settings,text='…',width=3,command=lambda k=key:self.browse(k)).grid(row=row,column=2,padx=(4,0))
        bottom=ttk.Frame(self);bottom.grid(row=2,column=0,columnspan=2,sticky='ew',pady=(8,0))
        for text,command in [('Open bank',self.open),('Save bank',self.save),('Size estimate',self.estimate)]:
            ttk.Button(bottom,text=text,command=lambda fn=command:self.guarded(fn)).pack(side='left',padx=(0,4))
        self.build_button = ttk.Button(bottom,text='Build ZDL',style='Accent.TButton',command=lambda:self.guarded(self.build))
        self.build_button.pack(side='right')
        self.patch_button = ttk.Button(bottom,text='Patch ZDL (no TI)',style='Accent.TButton',command=lambda:self.guarded(lambda:self.build(patch=True)))
        self.patch_button.pack(side='right',padx=(4,8))
        if os.environ.get('HYBRIDIR_ZDL_ENABLED') == '0':
            self.build_button.state(['disabled'])
        self.report=tk.StringVar(value='Add prepared models. Generic fitting remains unchanged. PNG title is baked into the image.')
        ttk.Label(self,textvariable=self.report,style='Small.TLabel',wraplength=900).grid(row=3,column=0,columnspan=2,sticky='w',pady=(8,0))
        self.app.tabs.bind('<<NotebookTabChanged>>',self.expand_tab,add='+')

    def mark_dirty(self):
        self.dirty=True

    def expand_tab(self,_event=None):
        if self.app.tabs.select()==str(self):
            self.app.after_idle(lambda:self.app.split.sashpos(0,max(250,self.app.split.winfo_height()-350)))

    def capture(self):
        return dict(project=copy.deepcopy(self.project),variables={k:v.get() for k,v in self.variables.items()},
                    dirty=self.dirty,selected=self.tree.selection(),report=self.report.get())

    def restore(self,state):
        self.project=state['project']
        for k,v in state['variables'].items():self.variables[k].set(v)
        self.refresh();self.dirty=state['dirty'];self.report.set(state['report'])
        valid=[i for i in state['selected'] if self.tree.exists(i)]
        if valid:self.tree.selection_set(valid)

    def guarded(self, command):
        if self.app.busy:
            self.app.status.set('Wait for the current operation to finish.')
            return
        try:command()
        except Exception as exc:self.app.error(exc)

    def sync(self):
        for key,value in self.variables.items():
            setattr(self.project,key,int(value.get()) if key=='fxid' else value.get())

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i,s in enumerate(self.project.slots):
            self.tree.insert('', 'end',iid=str(i),values=(s.label,len(s.model.fir) if s.model.fir_enabled else 0,
                                                       len(s.model.sections)+2,f'{s.model.output_gain_db:g}'))

    def selected(self):
        selection=self.tree.selection()
        if not selection:raise ValueError('Select an IR slot first')
        return int(selection[0])

    def append(self, model, label=None):
        from .zoom_bank import validate_model, ascii_label
        validate_model(model)
        if label is None:
            label=simpledialog.askstring('IR slot','1–7 ASCII characters:',initialvalue=f'IR{len(self.project.slots)+1}',parent=self)
        if label is None:return
        ascii_label(label)
        if label=='OFF':raise ValueError('OFF is reserved for bypass')
        if len(self.project.slots)>=8:raise ValueError('Compatibility envelope: at most 8 active slots')
        self.project.slots.append(Slot(label,model.clone()))
        self.mark_dirty();self.refresh()

    def current(self):
        if self.app.session.model is None:raise ValueError('Prepare or train a model first')
        self.append(self.app.session.model)

    def import_json(self):
        path=filedialog.askopenfilename(parent=self,filetypes=[('IRBQ model JSON','*.json')])
        if not path:return
        self.append(import_irbq_package(path))

    def import_wav(self):
        path=filedialog.askopenfilename(parent=self,filetypes=[('Impulse WAV','*.wav')])
        if not path:return
        taps=simpledialog.askinteger('FIR length','32–4096 samples after current preparation settings:',
                                    initialvalue=1024,minvalue=32,maxvalue=4096,parent=self)
        if taps is None:return
        session=Session(config=copy.deepcopy(self.app.session.config))
        session.config.fs=44100
        def prepare():
            session.load_audio(path)
            session.preprocess()
            fir=np.zeros(taps);n=min(taps,len(session.target));fir[:n]=session.target[:n]
            return Model(44100,fir,[],Path(path).stem)
        self.app.run_job(prepare,self.append,'Preparing WAV for Zoom bank…')

    def rename(self):
        i=self.selected()
        value=simpledialog.askstring('IR label','1–7 ASCII characters:',initialvalue=self.project.slots[i].label,parent=self)
        if value is None:return
        from .zoom_bank import ascii_label
        ascii_label(value)
        if value=='OFF':raise ValueError('OFF is reserved for bypass')
        self.project.slots[i].label=value;self.mark_dirty();self.refresh()

    def move(self, delta):
        i=self.selected();j=i+delta
        if not 0<=j<len(self.project.slots):return
        self.project.slots[i],self.project.slots[j]=self.project.slots[j],self.project.slots[i]
        self.mark_dirty();self.refresh();self.tree.selection_set(str(j))

    def remove(self):
        i=self.selected()
        if messagebox.askyesno('Remove slot',f'Remove {self.project.slots[i].label}?',parent=self):
            del self.project.slots[i];self.mark_dirty();self.refresh()

    def browse(self,key):
        path=(filedialog.askopenfilename(parent=self,filetypes=[('Card PNG','*.png')]) if key=='image'
              else filedialog.askdirectory(parent=self))
        if path:self.variables[key].set(path)

    def open(self):
        if self.dirty and not messagebox.askyesno('Unsaved bank','Discard current unsaved bank changes?',parent=self):return
        path=filedialog.askopenfilename(parent=self,filetypes=[('Zoom bank','*.zoombank.json'),('JSON','*.json')])
        if not path:return
        self.project=BankProject.load(path)
        for key,v in self.variables.items():v.set(str(getattr(self.project,key)))
        self.refresh();self.estimate();self.dirty=False

    def save(self):
        self.sync()
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.zoombank.json',initialfile='HYBRIDIR.zoombank.json')
        if path:self.project.save(path);self.dirty=False

    def estimate(self):
        self.sync();_,r=pack_bank(self.project)
        self.report.set(f"{r['active_slots']} slots · bank {r['bank_bytes']} B · estimated .const {r['estimated_const_bytes']} B · "
                        + '; '.join(r['warnings']))
        return r

    def build(self, patch=False):
        if not patch and os.environ.get('HYBRIDIR_ZDL_ENABLED') == '0':
            raise ValueError('ZDL building is disabled in this Trainer-only installation. Run full setup in a new folder.')
        self.sync();report=self.estimate()
        if not self.project.patched_folder:
            folder=filedialog.askdirectory(parent=self,title='Select the custom ZDL folder used by Zoom Effect Manager')
            if not folder:return
            self.project.patched_folder=folder;self.variables['patched_folder'].set(folder)
        conflicts=[e for e in catalog_entries(self.project) if (e['gid'],e['fxid'])==(self.project.gid,self.project.fxid)]
        replace_identity=False
        if conflicts:
            if all(e['name']==self.project.name and not e.get('reserved') for e in conflicts):
                if not messagebox.askyesno('Existing effect identity','This name and ID already exist. Build a replacement? Catalog files are not modified.',parent=self):return
                replace_identity=True
            else:
                free=suggest_free_id(self.project)
                if not messagebox.askyesno('ID occupied',f'ID {self.project.fxid} belongs to another effect. Use free ID {free}?',parent=self):return
                self.project.fxid=free;self.variables['fxid'].set(str(free))
        if report['estimated_const_bytes']>report['soft_const_budget']:
            if not messagebox.askyesno('Experimental bank','Estimated .const exceeds the conservative soft budget. Build for an explicit hardware test?',parent=self):return
        destination=filedialog.askdirectory(parent=self,title='ZDL output folder')
        if not destination:return
        target=Path(destination)/(self.project.filename+'.zdl')
        outputs=[target]
        if patch:outputs.append(Path(destination)/(self.project.filename+'.patch.json'))
        existing=[str(path) for path in outputs if path.exists()]
        overwrite=bool(existing)
        if overwrite and not messagebox.askyesno('Overwrite','Replace existing files?\n'+'\n'.join(existing),parent=self):return
        project=copy.deepcopy(self.project)
        builder=build_project
        if patch:
            from .zoom_patch import patch_project
            builder=patch_project
        self.app.run_job(lambda:builder(project,destination,overwrite,replace_identity),
                         lambda result:self.report.set(f'Built {result[0]} · SHA256 {result[1]["sha256"]} · hardware unverified'),
                         'Patching HYBRIDIR bank…' if patch else 'Building HYBRIDIR bank…', cancellable=False)
