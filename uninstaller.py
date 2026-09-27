"""Remove recorded installation files only; preserve personal or modified files."""
from pathlib import Path, PurePosixPath
import base64
import hashlib
import json
import os
import re
import subprocess
import sys

RECEIPT='uninstall-receipt.json'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def walk(root):
    """Enumerate without traversing directory links or Windows junctions."""
    pending=[Path(root)]
    while pending:
        folder=pending.pop()
        for path in folder.iterdir():
            yield path
            if not path.is_symlink() and not path.is_junction() and path.is_dir():pending.append(path)

def plain_path(path, root):
    """Never follow symlinks/junctions while removing installation files."""
    path=Path(path);root=Path(root)
    if not path.is_relative_to(root):return False
    return (all(not p.is_symlink() and not p.is_junction()
                for p in (path,*path.parents) if p==root or p.is_relative_to(root))
            and path.resolve().is_relative_to(root.resolve()))

def desktop_path():
    script="[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); $s=New-Object -ComObject WScript.Shell; $s.SpecialFolders.Item('Desktop')"
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',
        base64.b64encode(script.encode('utf-16le')).decode('ascii')],capture_output=True,check=True,
        timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    return Path(result.stdout.decode('utf-8-sig').strip())

def write_receipt(root, shortcut=None):
    root=Path(root).resolve()
    files=[]
    for path in sorted(walk(root)):
        if path.name==RECEIPT:continue
        if not plain_path(path,root):raise ValueError('Installation contains a link or junction')
        if path.is_file():files.append(dict(path=path.relative_to(root).as_posix(),sha256=digest(path)))
    record=dict(schema='hybridir-uninstall/1',root=str(root),files=files,shortcut=shortcut)
    with (root/RECEIPT).open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2)

def plan(root):
    root=Path(root).absolute()
    if not plain_path(root,root) or root==Path(root.anchor) or root==Path.home():
        raise ValueError('Unsafe installation folder')
    receipt=root/RECEIPT
    if not plain_path(receipt,root):raise ValueError('Invalid receipt path')
    record=json.loads(receipt.read_text(encoding='utf-8'))
    if record.get('schema')!='hybridir-uninstall/1' or Path(record['root'])!=root:
        raise ValueError('Receipt does not belong to this installation')
    shortcut=record.get('shortcut')
    if shortcut is not None:
        if (not isinstance(shortcut,dict) or set(shortcut)!={'path','sha256'}
                or not isinstance(shortcut['path'],str) or '\0' in shortcut['path']
                or not Path(shortcut['path']).is_absolute()
                or Path(shortcut['path']).name!='HYBRID IR.lnk'
                or not isinstance(shortcut['sha256'],str)
                or not re.fullmatch(r'[0-9a-f]{64}',shortcut['sha256'])):
            raise ValueError('Invalid shortcut receipt')
    selected=[];preserved=[];seen=set()
    runtime_roots={'.venv','.test-cache'}
    for item in record['files']:
        name=item['path'];rel=PurePosixPath(name)
        if (not name or '\\' in name or ':' in name or rel.is_absolute() or '..' in rel.parts
                or any(part.rstrip(' .')!=part for part in rel.parts)
                or name.casefold() in seen or name==RECEIPT):
            raise ValueError('Unsafe receipt entry')
        seen.add(name.casefold());path=root.joinpath(*rel.parts)
        if not plain_path(path,root):preserved.append(name);continue
        if not path.exists():continue
        current=digest(path) if path.is_file() else None
        if current and (rel.parts[0] in runtime_roots or current==item['sha256']):selected.append((path,current))
        else:preserved.append(name)
    if not {'launch.py','installer.py','uninstaller.py'} <= seen:
        raise ValueError('Incomplete installation receipt')
    # Private environment/cache trees belong to the app, not user exports.
    for path in walk(root):
        name=path.relative_to(root).as_posix()
        if name!=RECEIPT and (path.is_file() or path.is_symlink() or path.is_junction()) and name.casefold() not in seen:
            if path.relative_to(root).parts[0] in runtime_roots and plain_path(path,root) and path.is_file():
                selected.append((path,digest(path)))
            else:preserved.append(name)
    return root,record,selected,sorted(set(preserved))

def uninstall(root, remove_preferences=False):
    import importlib.util
    spec=importlib.util.spec_from_file_location('hybrid_installation_guard',Path(__file__).with_name('installation_guard.py'))
    guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
    with guard.installation_lock(root):
        return _uninstall(root,remove_preferences)


def _uninstall(root, remove_preferences=False):
    root,record,selected,preserved=plan(root)
    errors=[];removed=0
    controls={'uninstaller.py','Uninstall_HYBRIDIR.cmd','installation_guard.py'}
    deferred=[item for item in selected if item[0].relative_to(root).as_posix() in controls]
    for path,sha in selected:
        if path.relative_to(root).as_posix() in controls:continue
        try:
            if not plain_path(path,root) or digest(path)!=sha:
                preserved.append(path.relative_to(root).as_posix());continue
            path.unlink();removed+=1
        except OSError as exc:errors.append(f'{path.name}: {exc}')
    shortcut=record.get('shortcut')
    if shortcut and os.name=='nt':
        try:
            desktop=desktop_path();link=desktop/'HYBRID IR.lnk'
            if str(link)==shortcut['path'] and plain_path(link,desktop) and link.is_file():
                if digest(link)==shortcut['sha256']:link.unlink()
                else:preserved.append('Modified desktop shortcut')
            elif str(link)!=shortcut['path'] or not plain_path(link,desktop):
                preserved.append('Desktop shortcut path changed or linked; check it manually')
        except (OSError,subprocess.SubprocessError) as exc:errors.append('Desktop shortcut: '+str(exc))
    if remove_preferences:
        settings=Path(os.environ.get('APPDATA',Path.home()/'AppData/Roaming'))/'IRBQ_Lab/settings.json'
        if os.environ.get('IRBQ_SETTINGS_PATH'):
            preserved.append('Custom IRBQ_SETTINGS_PATH (remove manually if needed)')
        elif settings.exists():
            try:
                if (plain_path(settings,settings.parent)
                        and all(not p.is_symlink() and not p.is_junction() for p in (settings,*settings.parents))):
                    settings.unlink()
                    try:settings.parent.rmdir()
                    except OSError:pass
                else:preserved.append('Linked preferences file')
            except OSError as exc:errors.append('Preferences: '+str(exc))
    deleted_controls=[]
    if not errors:
        for path,sha in deferred:
            try:
                if plain_path(path,root) and digest(path)==sha:
                    content=path.read_bytes()
                    if hashlib.sha256(content).hexdigest()!=sha:
                        preserved.append(path.name);continue
                    path.unlink();removed+=1
                    deleted_controls.append((path,content))
                else:preserved.append(path.name)
            except OSError as exc:errors.append(f'{path.name}: {exc}');break
    if not errors:
        try:(root/RECEIPT).unlink()
        except OSError as exc:errors.append(f'{RECEIPT}: {exc}')
    if errors:
        # A late lock must not remove the entry point or its guard dependency.
        # Exclusive creation also preserves any concurrently-created replacement.
        for path,content in deleted_controls:
            try:
                with path.open('xb') as stream:stream.write(content)
                removed-=1
            except OSError as exc:errors.append(f'Restore {path.name}: {exc}')
    # rmdir removes only empty directories; never recursively delete a tree.
    for path in sorted(walk(root),key=lambda p:len(p.parts),reverse=True):
        if plain_path(path,root) and path.is_dir():
            try:path.rmdir()
            except OSError:pass
    if not errors:
        try:root.rmdir()
        except OSError:pass
    return dict(removed=removed,preserved=preserved,errors=errors,folder_remains=root.exists())

def main():
    import tkinter as tk
    from tkinter import ttk,messagebox
    root_path=Path(__file__).resolve().parent
    window=tk.Tk();window.title('Uninstall HYBRID IR');window.geometry('620x310')
    icon=root_path/'assets/zoom-ms70cdr.ico'
    if icon.is_file() and os.name=='nt':window.iconbitmap(str(icon))
    try:_,_,selected,preserved=plan(root_path)
    except Exception as exc:
        messagebox.showerror('Cannot uninstall',str(exc),parent=window);window.destroy();return
    body=ttk.Frame(window,padding=20);body.pack(fill='both',expand=True)
    ttk.Label(body,text='Uninstall HYBRID IR',font=('Segoe UI',18)).pack(anchor='w')
    ttk.Label(body,text=f'{len(selected)} recorded files will be removed.\n{len(preserved)} new or modified files will be kept.\nClose HYBRID IR before continuing.\nPersonal IRs, banks and ZEM folders are not removed.',wraplength=570).pack(anchor='w',pady=16)
    prefs=tk.BooleanVar(value=False)
    ttk.Checkbutton(body,text='Also remove shared IRBQ Lab language/theme settings',variable=prefs).pack(anchor='w')
    def execute():
        if not messagebox.askyesno('Confirm uninstall',f'Remove HYBRID IR from:\n{root_path}?',parent=window):return
        try:
            result=uninstall(root_path,prefs.get())
            text=f"Removed {result['removed']} files. Preserved {len(result['preserved'])} files/items."
            if result['preserved']:text+='\nKept: '+'; '.join(result['preserved'][:5])
            if result['errors']:text+='\nSome files could not be removed. Close the application and retry.\n'+'\n'.join(result['errors'][:4])
            elif result['folder_remains']:text+='\nThe installation folder remains because it contains preserved files.'
            messagebox.showinfo('Uninstall result',text,parent=window)
        except Exception as exc:messagebox.showerror('Uninstall error',str(exc),parent=window)
        window.destroy()
    ttk.Button(body,text='Uninstall',command=execute).pack(side='right',pady=16)
    ttk.Button(body,text='Cancel',command=window.destroy).pack(side='right',padx=8,pady=16)
    window.mainloop()

if __name__=='__main__':main()
