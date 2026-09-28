"""Exercise the actual PowerShell supervisor with automated Tk confirmation.

Only a newly created disposable fixture is removed. The UI driver is injected
into its copy of uninstaller.py, never the published application.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess


def smoke(source, work, supervisor=None):
    source=source.resolve();work=work.resolve()
    work.mkdir(parents=True,exist_ok=False)
    root=work/'app'
    root.mkdir()
    shutil.copytree(source/'runtime',root/'runtime',ignore=shutil.ignore_patterns('site-packages'))
    for name in ('uninstaller.py','installation_guard.py','standalone_uninstall.ps1','installer.py','launch.py'):
        shutil.copyfile(source/name,root/name)
    if supervisor is not None:
        shutil.copyfile(supervisor,root/'standalone_uninstall.ps1')
    driver='''import tkinter as _tk
from tkinter import ttk as _ttk, messagebox as _msg
_msg.askyesno=lambda *a,**kw: True
_msg.showinfo=lambda *a,**kw: print(a,flush=True)
def _error(*a,**kw): raise RuntimeError(str(a))
_msg.showerror=_error
def _loop(self,*a,**kw):
    self.withdraw()
    pending=list(self.winfo_children())
    while pending:
        widget=pending.pop()
        if isinstance(widget,_ttk.Button) and str(widget.cget('text'))=='Uninstall':
            widget.invoke()
            return
        pending.extend(widget.winfo_children())
    raise RuntimeError('Uninstall button not found')
_tk.Tk.mainloop=_loop
'''
    path=root/'uninstaller.py'
    path.write_text(driver+path.read_text(encoding='utf-8'),encoding='utf-8')
    entries=[dict(path=p.relative_to(root).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
             for p in root.rglob('*') if p.is_file()]
    (root/'PUBLICATION_MANIFEST.json').write_text(json.dumps(dict(schema='hybridir-publication/1',files=entries)),encoding='utf-8')
    # Load the unmodified owner implementation; the fixture driver is GUI-only.
    spec=importlib.util.spec_from_file_location('uninstall_smoke_owner',source/'uninstaller.py')
    owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
    owner.write_receipt(root)
    subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                    '-File',str(root/'standalone_uninstall.ps1')],cwd=work,check=True,timeout=180)
    if root.exists():raise AssertionError('Uninstall supervisor left application files')
    (work/'smoke.json').write_text(json.dumps({'powershell_supervisor':True,'automated_tk_confirmation':True}),encoding='utf-8')
    print('PASS: actual PowerShell staging / Tk confirmation / external deletion')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--supervisor',type=Path,help='Explicit source-level supervisor regression override')
    args=parser.parse_args();smoke(args.source,args.work,args.supervisor)
