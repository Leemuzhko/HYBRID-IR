"""Windows source installer. Uses an official Python 3.14 already installed.

No elevation, firmware downloads, or device access. Pip installs into the
selected destination. Runtime fragments are provisioned from user files.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import queue
import shutil
import subprocess
import sys
import threading
import venv
import webbrowser

SOURCE = Path(__file__).resolve().parent

def checked_payload(source):
    source = Path(source).resolve()
    manifest = json.loads((source / 'PUBLICATION_MANIFEST.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 'hybridir-publication/1':
        raise ValueError('Unsupported installation manifest')
    paths = []
    seen = set()
    for item in manifest['files']:
        name = item['path']
        relative = PurePosixPath(name)
        if (not name or '\\' in name or ':' in name or relative.is_absolute()
                or '..' in relative.parts or name.casefold() in seen):
            raise ValueError('Invalid or duplicate manifest path')
        seen.add(name.casefold())
        path = source.joinpath(*relative.parts)
        if not path.resolve().is_relative_to(source) or path.is_symlink() or not path.is_file():
            raise ValueError(f'Invalid installation file: {name}')
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError(f'Damaged installation file: {name}. Extract the archive again.')
        paths.append((name, path))
    return paths

def install(source, destination, ti_root='', donor_folder='', full=True, progress=lambda text: None):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError('Choose a new empty installation path. Existing installations are preserved.')
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Choose an installation path outside the extracted source folder.')
    payload = checked_payload(source)
    runtime = None
    if full:
        sys.path.insert(0, str(source / 'hybridir_sdk'))
        from sdk.runtime_setup import collect_runtime, check_compiler
        ti_root = str(check_compiler(ti_root))
        runtime = collect_runtime(donor_folder)
    destination.mkdir(parents=True)
    marker = destination / '.installation-incomplete'
    marker.write_text('Installation has not completed.\n', encoding='utf-8')
    progress('Copying verified application files...')
    for name, path in payload:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    shutil.copyfile(source / 'PUBLICATION_MANIFEST.json', destination / 'PUBLICATION_MANIFEST.json')
    if runtime is not None:
        from sdk.runtime_setup import write_runtime
        write_runtime(destination / 'hybridir_sdk', runtime)
    progress('Creating a private Python environment...')
    venv.EnvBuilder(with_pip=True).create(destination / '.venv')
    python = destination / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    progress('Installing dependencies from PyPI. This may take several minutes...')
    log = destination / 'installation.log'
    with log.open('w', encoding='utf-8') as stream:
        subprocess.run([str(python), '-m', 'pip', '--isolated', 'install',
                        '--index-url', 'https://pypi.org/simple', '--only-binary=:all:',
                        '-r', str(destination / 'requirements-zoom-lock.txt')],
                       stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=1200)
    progress('Checking the installed application...')
    subprocess.run([str(python), '-B', '-c',
                    'import tkinter,numpy,scipy,matplotlib,soundfile,PIL; '
                    'from irbq import gui,zoom_bank; '
                    'from sdk import build_effect'],
                   cwd=destination, env={**os.environ, 'PYTHONPATH':os.pathsep.join(
                       [str(destination/'irbq_lab'), str(destination/'hybridir_sdk')])}, check=True)
    if full:
        progress('Checking ZDL building with a temporary synthetic impulse...')
        code = ('import tempfile\nfrom pathlib import Path\nimport numpy as np\n'
                'from irbq.dsp import Model\n'
                'from irbq.zoom_bank import BankProject,Slot,build_project\n'
                'with tempfile.TemporaryDirectory(dir=Path.cwd(),prefix="install-check-") as td:\n'
                '    build_project(BankProject(slots=[Slot("UNIT",Model(44100,np.r_[.1,np.zeros(31)],[]))]),td)\n')
        with log.open('a', encoding='utf-8') as stream:
            subprocess.run([str(python), '-B', '-X', 'utf8', '-c', code], cwd=destination,
                           env={**os.environ, 'ZOOM_TI_ROOT':ti_root,
                                'PYTHONPATH':str(destination/'irbq_lab')},
                           stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=120)
    (destination / 'installation.json').write_text(json.dumps(
        {'schema':'hybridir-install/1', 'ti_root':str(Path(ti_root).resolve()) if full else '',
         'zdl_enabled':full}, indent=2), encoding='utf-8')
    (destination / 'Start_HYBRIDIR.cmd').write_text(
        '@echo off\r\ncd /d "%~dp0"\r\n".venv\\Scripts\\python.exe" -B -X utf8 launch.py %*\r\n'
        'if errorlevel 1 pause\r\n', encoding='utf-8')
    marker.unlink()
    progress('Installed. Open Start_HYBRIDIR.cmd in the installation folder.')
    return destination

def main():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    root = tk.Tk()
    root.title('HYBRID IR Setup')
    root.geometry('720x400')
    root.minsize(680, 380)
    body = ttk.Frame(root, padding=22)
    body.pack(fill='both', expand=True)
    body.columnconfigure(1, weight=1)
    ttk.Label(body, text='Install HYBRID IR', font=('Segoe UI',18)).grid(row=0,column=0,columnspan=3,sticky='w')
    ttk.Label(body, text='Trainer and ZDL bank builder · Windows · no administrator rights required').grid(
        row=1,column=0,columnspan=3,sticky='w',pady=(4,18))
    destination = tk.StringVar(value=str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'HYBRIDIR'))
    ti = tk.StringVar()
    donors = tk.StringVar()
    fields = [('Install to',destination),('TI C6000 compiler folder',ti),('Stock ZDL / runtime folder',donors)]
    controls = []
    for row,(label,variable) in enumerate(fields,2):
        ttk.Label(body,text=label).grid(row=row,column=0,sticky='w',padx=(0,12),pady=5)
        entry=ttk.Entry(body,textvariable=variable)
        entry.grid(row=row,column=1,sticky='ew',pady=5)
        def browse(v=variable):
            path=filedialog.askdirectory(parent=root)
            if path:
                # Destination is a NEW subfolder; prerequisite folders are used as selected.
                v.set(str(Path(path)/'HYBRIDIR') if v is destination else path)
        button=ttk.Button(body,text='Browse...',command=browse)
        button.grid(row=row,column=2,padx=(8,0))
        controls.extend((entry,button))
    full=tk.BooleanVar(value=True)
    choice=ttk.Checkbutton(body,text='Enable ZDL building (requires the compiler and stock files)',variable=full)
    choice.grid(row=5,column=0,columnspan=3,sticky='w',pady=(12,4));controls.append(choice)
    ttk.Button(body,text='Get TI compiler...',command=lambda:webbrowser.open('https://www.ti.com/tool/C6000-CGT')).grid(row=6,column=0,sticky='w')
    ttk.Label(body,text='Stock files: LineSel, ANA234CH, Exciter',wraplength=400).grid(
        row=6,column=1,columnspan=2,sticky='w',padx=(8,0))
    status=tk.StringVar(value='Dependencies are downloaded from PyPI during installation.')
    ttk.Label(body,textvariable=status,wraplength=660).grid(row=7,column=0,columnspan=3,sticky='w',pady=15)
    events=queue.Queue()
    busy=False
    def begin():
        nonlocal busy
        arguments=(SOURCE,destination.get(),ti.get(),donors.get(),full.get())
        busy=True
        for control in controls:control.configure(state='disabled')
        def worker():
            try:
                installed=install(*arguments,progress=lambda text:events.put(('progress',text)))
                events.put(('done',str(installed)))
            except Exception as error:events.put(('error',str(error)))
        threading.Thread(target=worker,daemon=False).start()
    install_button=ttk.Button(body,text='Install',command=begin)
    install_button.grid(row=8,column=2,sticky='e');controls.append(install_button)
    def poll():
        nonlocal busy
        while True:
            try:kind,text=events.get_nowait()
            except queue.Empty:break
            status.set(text)
            if kind in ('done','error'):
                busy=False
                for control in controls:control.configure(state='normal')
                if kind=='done':
                    messagebox.showinfo('Installed','Open Start_HYBRIDIR.cmd in:\n'+text,parent=root)
                    if os.name=='nt':os.startfile(text)
                else:messagebox.showerror('Installation failed',text+'\n\nIf files were copied, details are in installation.log. Choose a new destination to retry.',parent=root)
        root.after(100,poll)
    def close():
        if busy:messagebox.showinfo('Installation in progress','Please wait for installation to finish.',parent=root)
        else:root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    root.after(100,poll)
    root.mainloop()

if __name__ == '__main__':
    main()
