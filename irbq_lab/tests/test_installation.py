"""Install integrity and exact runtime provisioning without vendor fixtures."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'hybridir_sdk'))
from sdk import runtime_setup as runtime
installer_path = ROOT/'installer.py'
if not installer_path.exists():
    installer_path = ROOT/'packaging/hybridir/installer.py'
spec = importlib.util.spec_from_file_location('hybrid_installer', installer_path)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

class TestInstallation(unittest.TestCase):
    def test_standard_install_records_owned_files_and_uninstalls(self):
        uninstall_path=installer_path.with_name('uninstaller.py')
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'source';source.mkdir();destination=Path(td)/'installed'
            for name in ('installer.py','launch.py','requirements-zoom-lock.txt'):
                (source/name).write_bytes(b'fixture')
            (source/'uninstaller.py').write_bytes(uninstall_path.read_bytes())
            entries=[dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in source.iterdir()]
            (source/'PUBLICATION_MANIFEST.json').write_text(json.dumps(dict(schema='hybridir-publication/1',files=entries)))
            def make_venv(_self,path):
                path=Path(path);path.mkdir();(path/'owned.txt').write_bytes(b'private environment')
            with patch.object(installer.venv.EnvBuilder,'create',make_venv),patch.object(installer.subprocess,'run'),patch.object(installer,'create_desktop_shortcut') as shortcut:
                installer.install(source,destination,full=False)
                shortcut.assert_not_called()
            self.assertTrue((destination/'Uninstall_HYBRIDIR.cmd').is_file())
            spec=importlib.util.spec_from_file_location('installed_uninstall_test',destination/'uninstaller.py')
            uninstaller=importlib.util.module_from_spec(spec);spec.loader.exec_module(uninstaller)
            result=uninstaller.uninstall(destination)
            self.assertFalse(result['errors']);self.assertFalse(destination.exists())
            self.assertTrue((source/'uninstaller.py').exists())

    @unittest.skipUnless(os.name=='nt','Windows shortcut')
    def test_shortcut_real_com_and_existing_preserved(self):
        with tempfile.TemporaryDirectory(prefix="hybrid space ' тест ") as td:
            root=Path(td);app=root/'app';desktop=root/'desktop';desktop.mkdir()
            for relative in ('.venv/Scripts/pythonw.exe','launch.py','assets/zoom-ms70cdr.ico'):
                path=app/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture')
            installer.create_desktop_shortcut(app,desktop)
            link=desktop/'HYBRID IR.lnk'
            before=link.read_bytes();self.assertGreater(len(before),100)
            script=r'''[Console]::OutputEncoding = [Text.UTF8Encoding]::new(); $s = New-Object -ComObject WScript.Shell; $l = $s.CreateShortcut($env:HYBRID_TEST_LINK); @{target=$l.TargetPath; arguments=$l.Arguments; icon=$l.IconLocation; cwd=$l.WorkingDirectory} | ConvertTo-Json -Compress'''
            result=installer.subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',
                installer.base64.b64encode(script.encode('utf-16le')).decode('ascii')],
                env={**os.environ,'HYBRID_TEST_LINK':str(link)},capture_output=True,check=True,timeout=30,
                creationflags=installer.subprocess.CREATE_NO_WINDOW)
            props=json.loads(result.stdout.decode('utf-8-sig'))
            self.assertEqual(Path(props['target']),app/'.venv/Scripts/pythonw.exe')
            self.assertEqual(props['arguments'],f'-B -X utf8 "{app / "launch.py"}"')
            self.assertEqual(Path(props['cwd']),app)
            self.assertEqual(props['icon'],str(app/'assets/zoom-ms70cdr.ico')+',0')
            with self.assertRaises(installer.subprocess.CalledProcessError):
                installer.create_desktop_shortcut(app,desktop)
            self.assertEqual(link.read_bytes(),before)

    @unittest.skipUnless(os.name=='nt','Windows GUI')
    def test_setup_developer_visibility(self):
        import tkinter as tk
        from tkinter import ttk
        def inspect(root):
            root.withdraw()
            widgets=list(root.winfo_children()[0].winfo_children())
            labels={str(w.cget('text')):w for w in widgets if isinstance(w,(ttk.Label,ttk.Checkbutton))}
            field=labels['TI C6000 compiler folder']
            self.assertEqual(field.winfo_manager(),'')
            toggle=next(w for label,w in labels.items() if label.startswith('Developer:'))
            toggle.invoke();self.assertEqual(field.winfo_manager(),'grid')
            toggle.invoke();self.assertEqual(field.winfo_manager(),'')
            self.assertIn('Create a desktop shortcut',labels)
            root.destroy()
        with patch.object(tk.Tk,'mainloop',inspect):installer.main()

    def manifest(self, root, name='payload.txt', digest=None):
        (root/'PUBLICATION_MANIFEST.json').write_text(json.dumps({
            'schema':'hybridir-publication/1', 'files':[{
                'path':name, 'sha256':digest or hashlib.sha256(b'content').hexdigest()}]}), encoding='utf-8')

    def test_manifest_integrity_and_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'payload.txt').write_bytes(b'content')
            self.manifest(root)
            self.assertEqual(installer.checked_payload(root)[0][0], 'payload.txt')
            (root/'payload.txt').write_bytes(b'damaged')
            with self.assertRaisesRegex(ValueError,'Damaged'):installer.checked_payload(root)
            for name in ('../payload.txt','C:/payload.txt','/payload.txt','..\\payload.txt'):
                self.manifest(root,name)
                with self.assertRaises(ValueError):installer.checked_payload(root)

    def test_existing_destination_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'keep.txt';path.write_bytes(b'keep')
            with self.assertRaisesRegex(ValueError,'Existing installations'):
                installer.install(Path(td)/'source',td,full=False)
            self.assertEqual(path.read_bytes(),b'keep')

    def test_runtime_exact_slice_and_corruption(self):
        data=b'fixture-only-runtime'
        recipe={'donor':'TEST.ZDL','offset':128,'size':len(data),
                'sha256':hashlib.sha256(data).hexdigest()}
        with tempfile.TemporaryDirectory() as td, patch.object(runtime,'RECIPES',{'test.bin':recipe}):
            root=Path(td);donors=root/'donors';donors.mkdir()
            raw=bytearray(128+len(data));raw[:8]=b'\0\0\0\0SIZE';raw[0x4c:0x50]=b'\x7fELF';raw[128:]=data
            donor=donors/'renamed.ZDL';donor.write_bytes(raw)
            collected=runtime.collect_runtime(donors)
            sdk=root/'sdk';runtime.write_runtime(sdk,collected);runtime.verify_runtime(sdk)
            self.assertEqual((sdk/'build/test.bin').read_bytes(),data)
            (sdk/'build/test.bin').write_bytes(b'keep-existing')
            with self.assertRaisesRegex(ValueError,'preserved'):runtime.write_runtime(sdk,collected)
            self.assertEqual((sdk/'build/test.bin').read_bytes(),b'keep-existing')
            raw[-1]^=1;donor.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'Matching stock files'):runtime.collect_runtime(donors)

    def test_partial_bundle_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as td:
            sdk=Path(td)/'sdk'
            with self.assertRaisesRegex(ValueError,'incomplete'):runtime.write_runtime(sdk,{})
            self.assertFalse(sdk.exists())

    def test_compiler_version_and_bin_folder_normalization(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'bin').mkdir();(root/'include').mkdir()
            (root/'bin/cl6x.exe').write_bytes(b'fixture');(root/'include/stdint.h').write_bytes(b'')
            with patch.object(runtime.subprocess,'run',return_value=SimpleNamespace(stdout='8.5.0\n')):
                self.assertEqual(runtime.check_compiler(root/'bin'),root.resolve())
            with patch.object(runtime.subprocess,'run',return_value=SimpleNamespace(stdout='8.3.0\n')):
                with self.assertRaisesRegex(ValueError,'requires TI'):runtime.check_compiler(root)

if __name__=='__main__':unittest.main()
