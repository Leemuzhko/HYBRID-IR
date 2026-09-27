"""A bank tab in the existing Trainer, not a replacement application."""
import copy
import os
import hashlib
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import numpy as np
from .dsp import Model
from .project import Session
from .i18n import tr
from .zoom_variable_patch import bank_usage
from .zoom_rbj_bank import bq_count, legacy_candidates, assign_roles
from .zoom_bank import BankProject, Slot, pack_bank, build_project, catalog_entries, suggest_free_id, import_irbq_package


class ZoomPanel(ttk.Frame):
    def __init__(self, app, parent):
        super().__init__(parent, padding=8)
        self.app = app
        self.project = BankProject()
        self.dirty = False
        self.project_path = None
        self.edit_uid = None
        self.edit_digest = None
        self.variables = {}
        self.budget_job = None
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=0, minsize=340)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text='Zoom bank · OFF is automatic · hardware slot limit not established',
                  style='Small.TLabel').grid(row=0, column=0, columnspan=2, sticky='w', pady=(0,4))
        left=ttk.Frame(self);left.grid(row=1,column=0,sticky='nsew',padx=(0,12))
        left.columnconfigure(0,weight=1);left.rowconfigure(0,weight=1)
        self.tree=ttk.Treeview(left,columns=('label','fir','bq','gain'),show='headings',height=12,selectmode='browse')
        self.tree.bind('<Double-1>', lambda e:self.guarded(self.edit_slot))
        for key,label,width in [('label','IR label',110),('fir','FIR taps',70),('bq','BQ total',70),('gain','Gain dB',70)]:
            self.tree.heading(key,text=label);self.tree.column(key,width=width,anchor='w' if key=='label' else 'e')
        self.tree.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(left,orient='vertical',command=self.tree.yview)
        scroll.grid(row=0,column=1,sticky='ns');self.tree.configure(yscrollcommand=scroll.set)
        actions=ttk.Frame(left);actions.grid(row=1,column=0,columnspan=2,sticky='w',pady=(4,0))
        for index,(text,command) in enumerate([('Current model',self.current),('Edit in Trainer',self.edit_slot),('Update slot',self.update_slot)]):
            ttk.Button(actions,text=tr(text),style='Compact.TButton',command=lambda fn=command:self.guarded(fn)).grid(row=0,column=index,sticky='ew',padx=(0,4),pady=2)
        secondary=ttk.Frame(actions);secondary.grid(row=1,column=0,columnspan=3,sticky='w')
        importer=ttk.Menubutton(secondary,text=tr('Import'),style='Compact.TMenubutton');importer.pack(side='left',padx=(0,4))
        menu=tk.Menu(importer,tearoff=False);importer.configure(menu=menu)
        for text,fn in [('Import JSON',self.import_json),('Import WAV',self.import_wav)]:menu.add_command(label=tr(text),command=lambda f=fn:self.guarded(f))
        for text,fn in [('Rename',self.rename),('Remove',self.remove),('↑',lambda:self.move(-1)),('↓',lambda:self.move(1))]:
            ttk.Button(secondary,text=tr(text),style='Compact.TButton',width=3 if text in ('↑','↓') else None,command=lambda f=fn:self.guarded(f)).pack(side='left',padx=(0,4))
        from .gui import ScrollPanel
        self.settings_scroll=ScrollPanel(self);self.settings_scroll.grid(row=1,column=1,sticky='nsew')
        settings=self.settings_scroll.body
        settings.configure(padding=0)
        settings.columnconfigure(1,weight=1)
        identity=ttk.Frame(settings);identity.grid(row=0,column=0,columnspan=3,sticky='ew',pady=(0,8))
        identity.columnconfigure(0,weight=1);identity.columnconfigure(1,weight=1)
        position=1
        for key,label in [('name','Display name'),('filename','ZDL basename'),('fxid','Effect ID'),
                                           ('image','Card PNG'),('patched_folder','Zoom Effect Manager custom folder:')]:
            v=tk.StringVar(value=str(getattr(self.project,key)));self.variables[key]=v
            v.trace_add('write',lambda *_:self.mark_dirty())
            if key in ('name','filename','fxid'):
                column=('name','filename','fxid').index(key)
                ttk.Label(identity,text=tr(label),style='Small.TLabel').grid(row=0,column=column,sticky='w',padx=(0,8))
                ttk.Entry(identity,textvariable=v,width=5 if key=='fxid' else 12,style='Compact.TEntry').grid(row=1,column=column,sticky='ew',padx=(0,8) if column<2 else 0)
            else:
                row=position;position+=2
                ttk.Label(settings,text=tr(label),style='Small.TLabel').grid(row=row,column=0,columnspan=3,sticky='w')
                ttk.Entry(settings,textvariable=v,width=20,style='Compact.TEntry').grid(row=row+1,column=0,columnspan=2,sticky='ew',pady=(0,4))
                ttk.Button(settings,text='…',width=3,style='Compact.TButton',command=lambda k=key:self.browse(k)).grid(row=row+1,column=2,padx=(4,0))
        bottom=ttk.Frame(self);bottom.grid(row=2,column=0,columnspan=2,sticky='ew',pady=(4,0))
        ttk.Button(bottom,text=tr('New bank'),style='Compact.TButton',command=lambda:self.guarded(self.new)).pack(side='left',padx=(0,4))
        bank_menu=ttk.Menubutton(bottom,text=tr('Bank'),style='Compact.TMenubutton');bank_menu.pack(side='left',padx=(0,4))
        menu=tk.Menu(bank_menu,tearoff=False);bank_menu.configure(menu=menu)
        for text,command in [('New bank',self.new),('Open bank',self.open),('Save bank as…',lambda:self.save(True)),('Size estimate',self.estimate)]:
            menu.add_command(label=tr(text),command=lambda fn=command:self.guarded(fn))
        ttk.Button(bottom,text=tr('Save bank'),style='Compact.TButton',command=lambda:self.guarded(self.save)).pack(side='left')
        self.build_button = ttk.Button(bottom,text='Build ZDL',style='Compact.TButton',command=lambda:self.guarded(self.build))
        self.build_button.pack(side='right')
        self.patch_button = ttk.Button(bottom,text='Patch ZDL (no TI)',style='Accent.TButton',command=lambda:self.guarded(lambda:self.build(patch=True)))
        self.patch_button.pack(side='right',padx=(4,8))
        if os.environ.get('HYBRIDIR_ZDL_ENABLED') == '0':
            self.build_button.state(['disabled'])
        self.report=tk.StringVar(value='Add prepared models. Generic fitting remains unchanged. PNG title is baked into the image.')
        self.report.trace_add('write',lambda *_:self.app.status.set(self.report.get()) if hasattr(self.app,'status') else None)
        budget = ttk.Frame(settings)
        budget.grid(row=5,column=0,columnspan=3,sticky='ew',pady=(8,0))
        self.budget_frame = budget
        budget.columnconfigure(1,weight=1)
        self.capacity_text = tk.StringVar()
        self.template_text = tk.StringVar()
        self.capacity_bar = ttk.Progressbar(budget,maximum=100,style='Compact.Horizontal.TProgressbar')
        self.template_bar = ttk.Progressbar(budget,maximum=100,style='Compact.Horizontal.TProgressbar')
        self.capacity_brief=tk.StringVar(value=tr('Bank size'))
        self.template_brief=tk.StringVar(value=tr('Bank slots'))
        for row, title, bar, text in (
            (0, 'HVB4RBJ .const budget', self.capacity_bar, self.capacity_text),
            (1, 'Variable bank loading profile', self.template_bar, self.template_text)):
            ttk.Label(budget,textvariable=self.capacity_brief if row==0 else self.template_brief,style='Small.TLabel',wraplength=310).grid(row=row*2,column=0,columnspan=2,sticky='w')
            bar.grid(row=row*2+1,column=0,columnspan=2,sticky='ew',pady=(4,8))
        self.bank_title = tk.StringVar(value=tr('New bank'))
        ttk.Label(settings,textvariable=self.bank_title,style='Small.TLabel',wraplength=310).grid(row=6,column=0,columnspan=3,sticky='w',pady=4)
        self.edit_title = tk.StringVar()
        ttk.Label(settings,textvariable=self.edit_title,style='Small.TLabel',wraplength=310).grid(row=7,column=0,columnspan=3,sticky='w')
        self.recent = ttk.Combobox(settings,values=self.app.prefs.recent_banks,state='readonly',width=40)
        self.recent_menu=tk.Menu(menu,tearoff=False)
        menu.add_cascade(label=tr('Recent banks'),menu=self.recent_menu)
        self.refresh_recent()
        self.settings_scroll.bind_wheel_tree(settings)
        self.bind('<Destroy>',self.cancel_budget,add='+')
        self.schedule_budget()
        self.app.tabs.bind('<<NotebookTabChanged>>',self.expand_tab,add='+')

    def mark_dirty(self):
        self.dirty=True
        if hasattr(self, 'bank_title'):self.bank_title.set((Path(self.project_path).name if self.project_path else tr('New bank'))+' *')
        self.schedule_budget()

    def refresh_recent(self):
        self.recent.configure(values=self.app.prefs.recent_banks)
        self.recent_menu.delete(0,'end')
        for path in self.app.prefs.recent_banks:
            self.recent_menu.add_command(label=Path(path).name,command=lambda p=path:self.guarded(lambda:self.open(p)))

    def schedule_budget(self):
        if hasattr(self, 'capacity_bar'):
            if self.budget_job is not None:self.app.after_cancel(self.budget_job)
            # App.destroy cancels all timers; register with that same Tcl owner.
            self.budget_job = self.app.after(200, self.scheduled_budget)

    def scheduled_budget(self):
        # Tk owns deletion of the callback currently executing.
        self.budget_job = None
        self.update_budget()

    def cancel_budget(self, event):
        if event.widget == self and self.budget_job is not None:
            self.app.after_cancel(self.budget_job)
            self.budget_job = None

    def update_budget(self):
        if self.budget_job is not None:
            self.app.after_cancel(self.budget_job)
            self.budget_job = None
        try:
            preview = copy.copy(self.project)
            preview.image = self.variables['image'].get()
            usage = bank_usage(preview)
            self.capacity_bar['value'] = min(100, 100*usage['const_bytes']/usage['const_budget'])
            self.template_bar['value'] = min(100, 100*usage['active_slots']/8)
            remaining = usage['remaining_bytes']
            self.capacity_brief.set(tr('Bank .const: {used}/{limit} B · free {remaining} B').format(used=usage['const_bytes'],limit=usage['const_budget'],remaining=remaining))
            self.template_brief.set(tr('Slots {slots}/8 · FIR {fir} · BQ {bq}').format(slots=usage['active_slots'],fir=usage['limits']['fir_pool'][0],bq=usage['limits']['bq_pool'][0]))
            self.capacity_text.set(tr('{used} / {limit} B; remaining {remaining} B; RBJ parameters {params} B; gain LUT {lut} B; code + const {total}/{cap} B').format(
                used=usage['const_bytes'],limit=usage['const_budget'],remaining=remaining,
                params=usage['rbj_parameter_bytes']+usage['common_pres_parameter_bytes'],lut=usage['gain_lut_bytes'],
                total=usage['code_const_bytes'],cap=usage['code_const_cap']))
            limits=usage['limits']
            status=tr('Capacity fits; hardware unverified' if usage['template_fits'] else 'Template capacity exceeded')
            titles={'slots':'Slots','fir_pool':'FIR pool','bq_pool':'BQ pool',
                    'max_fir':'FIR per slot','max_bq':'BQ per slot','image':'Card image'}
            exceeded=[f'{tr(titles[key])} {n}/{limit}' for key,(n,limit) in limits.items() if n>limit]
            if exceeded:status+=': '+', '.join(exceeded)
            if not usage['template_fits']:self.template_brief.set(tr('Template capacity exceeded'))
            if not self.project.slots:status=tr('Add at least one model')
            self.template_text.set(tr('Slots {slots}; FIR pool {fir}; BQ pool {bq}; {status}').format(
                slots='/'.join(map(str,limits['slots'])),fir='/'.join(map(str,limits['fir_pool'])),
                bq='/'.join(map(str,limits['bq_pool'])),
                status=status))
            return usage
        except Exception as exc:
            self.capacity_bar['value']=0;self.template_bar['value']=0
            self.capacity_text.set(tr('Capacity unavailable: {error}').format(error=tr(str(exc))))
            self.capacity_brief.set(self.capacity_text.get());self.template_brief.set('')
            self.template_text.set('')
            return None

    def expand_tab(self,_event=None):
        if self.app.tabs.select()==str(self):self.app.expand_catalog()

    def capture(self):
        return dict(project=copy.deepcopy(self.project),variables={k:v.get() for k,v in self.variables.items()},
                    dirty=self.dirty,selected=self.tree.selection(),report=self.report.get(),
                    path=self.project_path,edit_uid=self.edit_uid,edit_digest=self.edit_digest)

    def restore(self,state):
        self.project=state['project']
        self.project_path=state.get('path');self.edit_uid=state.get('edit_uid');self.edit_digest=state.get('edit_digest')
        for k,v in state['variables'].items():self.variables[k].set(v)
        self.refresh();self.dirty=state['dirty'];self.report.set(state['report'])
        self.refresh_titles()
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
                                                       bq_count(s.model),f'{s.model.output_gain_db:g}'))
        self.schedule_budget()

    def selected(self):
        selection=self.tree.selection()
        if not selection:raise ValueError('Select an IR slot first')
        return int(selection[0])

    def prepare_roles(self, model):
        """Migration affects a bank clone only; Cancel is transactionally inert."""
        model=model.clone()
        candidates=legacy_candidates(model)
        if candidates:
            choice=messagebox.askyesnocancel(tr('Legacy Trainer controls'),tr(
                'Use the Resonance filter in this older model as RESO? Yes: reuse it, preserving its neutral response. '
                'No: keep all filters as corrections and add default RESO/PRES. Presence stays a correction filter. '
                'Cancel: leave the bank unchanged.'),parent=self)
            if choice is None:return None
            if choice:model=assign_roles(model,candidates)
        bq_count(model)  # Fail closed on invalid explicit metadata.
        return model

    def append(self, model, label=None, session=None):
        from .zoom_bank import validate_model, ascii_label
        validate_model(model)
        if label is None:
            label=simpledialog.askstring('IR slot','1–7 ASCII characters:',initialvalue=f'IR{len(self.project.slots)+1}',parent=self)
        if label is None:return
        ascii_label(label)
        if label=='OFF':raise ValueError('OFF is reserved for bypass')
        if len(self.project.slots)>=8:raise ValueError('Compatibility envelope: at most 8 active slots')
        model=self.prepare_roles(model)
        if model is None:return
        stored=copy.deepcopy(session) if session is not None else None
        if stored is not None:stored.model=model.clone()
        self.project.slots.append(Slot(label,model,stored))
        self.mark_dirty();self.refresh()

    def current(self):
        if self.app.session.model is None:raise ValueError('Prepare or train a model first')
        self.append(self.app.session.model, session=self.app.session)

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
        self.app.run_job(prepare,lambda model:self.append(model, session=session),'Preparing WAV for Zoom bank…')

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

    def confirm_bank(self):
        if not self.dirty:return True
        choice=messagebox.askyesnocancel(tr('Unsaved bank'),tr('Save bank changes before continuing?'),parent=self)
        return choice is not None and (not choice or self.save())

    def new(self):
        if self.edit_uid and self.app.dirty and not self.app.confirm_session(discard=self.discard_slot_edit):return
        if not self.confirm_bank():return
        project=BankProject(patched_folder=self.variables['patched_folder'].get())
        project.fxid=suggest_free_id(project)
        self.project=project;self.project_path=None;self.edit_uid=None;self.edit_digest=None
        for key,v in self.variables.items():v.set(str(getattr(project,key)))
        self.refresh();self.dirty=False;self.refresh_titles()

    def open(self, path=None):
        if path is None:path=filedialog.askopenfilename(parent=self,filetypes=[('Portable bank','*.hybridbank'),('Zoom bank','*.zoombank.json'),('JSON','*.json')])
        if not path:return
        if self.edit_uid and self.app.dirty and not self.app.confirm_session(discard=self.discard_slot_edit):return
        if not self.confirm_bank():return
        project=BankProject.load(path)
        # Destination folder is a local setting, not part of portable data.
        if not project.patched_folder:project.patched_folder=self.variables['patched_folder'].get()
        migrated=False
        for slot in project.slots:
            model=self.prepare_roles(slot.model)
            if model is None:return
            migrated=migrated or model.to_dict()!=slot.model.to_dict()
            slot.model=model
            if slot.session is not None:slot.session.model=model.clone()
        self.project=project
        self.project_path=str(path);self.edit_uid=None;self.edit_digest=None
        for key,v in self.variables.items():v.set(str(getattr(self.project,key)))
        self.refresh();self.estimate();self.dirty=migrated
        self.app.remember_path('recent_banks',path);self.refresh_recent()
        self.refresh_titles()

    def save(self, save_as=False):
        self.sync()
        path=self.project_path
        choose=save_as or not path
        if choose:path=filedialog.asksaveasfilename(parent=self,defaultextension='.hybridbank',confirmoverwrite=False,
            filetypes=[('Portable bank','*.hybridbank'),('Legacy models only','*.zoombank.json')],
            initialfile=Path(self.project_path).name if self.project_path else 'HYBRIDIR.hybridbank')
        if not path:return False
        if choose and Path(path).exists() and not messagebox.askyesno(tr('Replace bank?'),str(path),parent=self):return False
        if Path(path).suffix.lower()!='.hybridbank' and any(s.session is not None for s in self.project.slots):
            if not messagebox.askyesno(tr('Models only'),tr('JSON does not retain references or training history. Save models only?'),parent=self):return False
        self.project.save(path);self.project_path=str(path);self.dirty=False
        self.app.remember_path('recent_banks',path);self.refresh_recent()
        self.refresh_titles();return True

    def refresh_titles(self):
        self.bank_title.set((Path(self.project_path).name if self.project_path else tr('New bank'))+(' *' if self.dirty else ''))
        slot=next((s for s in self.project.slots if s.uid==self.edit_uid),None)
        self.edit_title.set(tr('Editing slot: {label}').format(label=slot.label) if slot else '')

    @staticmethod
    def digest(model):
        return hashlib.sha256(json.dumps(model.to_dict(),sort_keys=True,allow_nan=False).encode()).hexdigest()

    def edit_slot(self):
        from .authoring import model_session
        slot=self.project.slots[self.selected()]
        if not self.app.confirm_session():return
        session=copy.deepcopy(slot.session) if slot.session is not None else model_session(slot.model)
        session.model=slot.model.clone()
        self.app.install_session(session)
        self.edit_uid=slot.uid;self.edit_digest=self.digest(slot.model);self.refresh_titles()
        self.app.tabs.select(0)

    def discard_slot_edit(self):
        """Discard restores the bank's copy; it must not leave a dirty orphan."""
        from .authoring import model_session
        uid,digest=self.edit_uid,self.edit_digest
        slot=next((s for s in self.project.slots if s.uid==uid),None)
        if slot is None:session=Session()
        else:
            session=copy.deepcopy(slot.session) if slot.session is not None else model_session(slot.model)
            session.model=slot.model.clone()
        self.app.install_session(session)
        # Retain the old binding if navigation is subsequently cancelled.
        self.edit_uid=uid if slot else None;self.edit_digest=digest if slot else None
        self.refresh_titles()

    def update_slot(self):
        if not self.app.guard_model():return
        slot=next((s for s in self.project.slots if s.uid==self.edit_uid),None)
        if slot is None:raise ValueError('The edited slot is no longer in this bank')
        if self.digest(slot.model)!=self.edit_digest:
            if not messagebox.askyesno(tr('Slot changed'),tr('The bank slot changed after editing began. Replace it?'),parent=self):return
        model=self.prepare_roles(self.app.session.model)
        if model is None:return
        from .zoom_bank import validate_model
        validate_model(model)
        session=copy.deepcopy(self.app.session);session.model=model.clone()
        slot.model=model;slot.session=session;self.edit_digest=self.digest(model)
        self.mark_dirty();self.refresh();self.app.dirty=False;self.refresh_titles()

    def estimate(self):
        self.sync();r=bank_usage(self.project)
        self.report.set(tr('{slots} slots · bank {bank} B · .const {const}/{budget} B · role/fade kernel: hardware unverified').format(
            slots=r['active_slots'],bank=r['bank_bytes'],const=r['const_bytes'],budget=r['const_budget']))
        return r

    def build(self, patch=False):
        if not patch and os.environ.get('HYBRIDIR_ZDL_ENABLED') == '0':
            raise ValueError('ZDL building is disabled in this Trainer-only installation. Run full setup in a new folder.')
        if not patch and any(b.control_role for s in self.project.slots for b in s.model.sections):
            raise ValueError('Use Patch ZDL for role-aware models; the legacy TI builder adds default controls')
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
        if patch and not bank_usage(self.project)['template_fits']:
            raise ValueError('Bank/image exceeds conservative HVB4RBJ loading profile')
        if not patch:
            _,legacy_report=pack_bank(self.project)
            if legacy_report['estimated_const_bytes']>legacy_report['soft_const_budget']:
                if not messagebox.askyesno('Experimental bank','Estimated .const exceeds the conservative soft budget. Build for an explicit hardware test?',parent=self):return
        destination=self.project.patched_folder
        target=Path(destination)/(self.project.filename+'.zdl')
        outputs=[target]
        if patch:
            from .zoom_export import package_paths
            outputs = list(package_paths(self.project, destination).values())
        existing=[str(path) for path in outputs if path.exists()]
        overwrite=bool(existing)
        if overwrite and not messagebox.askyesno('Overwrite','Replace existing files?\n'+'\n'.join(existing),parent=self):return
        project=copy.deepcopy(self.project)
        builder=build_project
        if patch:
            from .zoom_variable_patch import patch_project
            builder=patch_project
        self.app.run_job(lambda:builder(project,destination,overwrite,replace_identity),
                         self.export_complete,
                         'Patching HYBRIDIR bank…' if patch else 'Building HYBRIDIR bank…', cancellable=False)

    def export_complete(self, result):
        path,report=result
        self.report.set(f'Built {path} · SHA256 {report["sha256"]} · hardware unverified')
        messagebox.showinfo(tr('ZDL export'),tr('ZDL saved successfully.\n{path}').format(
            path=Path(path).resolve()),parent=self)
