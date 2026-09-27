import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
path=ROOT/'uninstaller.py'
if not path.exists():path=ROOT/'packaging/hybridir/uninstaller.py'
spec=importlib.util.spec_from_file_location('uninstall_test_module',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class TestUninstall(unittest.TestCase):
    def setup_app(self,root):
        root.mkdir()
        for name in ('launch.py','installer.py','uninstaller.py','.venv/package.py','assets/icon.ico'):
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'owned')
        module.write_receipt(root)

    def test_owned_runtime_removed_personal_and_modified_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'app';self.setup_app(root)
            (root/'my-bank.json').write_bytes(b'personal')
            (root/'launch.py').write_bytes(b'user edited')
            cache=root/'.test-cache/new';cache.parent.mkdir();cache.write_bytes(b'cache')
            (root/'.venv/new.pyc').write_bytes(b'cache')
            result=module.uninstall(root)
            self.assertFalse(result['errors'])
            self.assertEqual((root/'my-bank.json').read_bytes(),b'personal')
            self.assertEqual((root/'launch.py').read_bytes(),b'user edited')
            self.assertFalse((root/'.venv').exists());self.assertFalse(cache.exists())
            self.assertTrue(result['folder_remains'])

    def test_clean_uninstall_and_settings_opt_in(self):
        with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'APPDATA':td,'IRBQ_SETTINGS_PATH':''}):
            settings=Path(td)/'IRBQ_Lab/settings.json';settings.parent.mkdir();settings.write_text('{}')
            root=Path(td)/'app';self.setup_app(root)
            self.assertFalse(module.uninstall(root)['folder_remains'])
            self.assertTrue(settings.exists())
            self.setup_app(root);module.uninstall(root,remove_preferences=True)
            self.assertFalse(settings.exists())

    def test_receipt_traversal_rejected_before_deletion(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'app';self.setup_app(root)
            outside=Path(td)/'keep';outside.write_bytes(b'owned')
            receipt=root/module.RECEIPT;data=json.loads(receipt.read_text())
            data['files'].append(dict(path='../keep',sha256=module.digest(outside)))
            receipt.write_text(json.dumps(data))
            with self.assertRaises(ValueError):module.uninstall(root)
            self.assertTrue((root/'launch.py').exists());self.assertTrue(outside.exists())
            for name in ('.. /keep','folder./keep','file:stream','/absolute','C:/outside'):
                data['files'][-1]['path']=name;receipt.write_text(json.dumps(data))
                with self.assertRaises(ValueError):module.uninstall(root)
                self.assertTrue((root/'launch.py').exists());self.assertTrue(outside.exists())

    def test_locked_file_keeps_uninstaller_and_receipt_for_retry(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'app';self.setup_app(root)
            real_unlink=Path.unlink
            def locked(path,*args,**kwargs):
                if path.name=='package.py':raise PermissionError('simulated lock')
                return real_unlink(path,*args,**kwargs)
            with patch.object(Path,'unlink',locked):result=module.uninstall(root)
            self.assertTrue(result['errors'])
            self.assertTrue((root/'uninstaller.py').exists())
            self.assertTrue((root/module.RECEIPT).exists())
            self.assertFalse(module.uninstall(root)['folder_remains'])

    def test_malformed_shortcut_rejected_before_any_deletion(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'app';self.setup_app(root)
            receipt=root/module.RECEIPT;data=json.loads(receipt.read_text())
            for shortcut in ({'sha256':'x'},'invalid',{},
                             dict(path='relative.lnk',sha256='0'*64),
                             dict(path=str(Path(td)/'HYBRID IR.lnk'),sha256='x')):
                data['shortcut']=shortcut;receipt.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,'shortcut'):module.uninstall(root)
                self.assertTrue((root/'launch.py').exists())
                self.assertTrue((root/'.venv/package.py').exists())

    def test_locked_control_or_receipt_restores_runnable_uninstaller(self):
        for locked_name in ('installation_guard.py','uninstaller.py','Uninstall_HYBRIDIR.cmd',module.RECEIPT):
            with self.subTest(locked_name=locked_name),tempfile.TemporaryDirectory() as td:
                root=Path(td)/'app';root.mkdir()
                for name in ('uninstaller.py','installation_guard.py'):
                    (root/name).write_bytes(Path(module.__file__).with_name(name).read_bytes())
                for name in ('launch.py','installer.py','Uninstall_HYBRIDIR.cmd'):
                    (root/name).write_bytes(b'owned')
                module.write_receipt(root)
                real_unlink=Path.unlink
                def locked(path,*args,**kwargs):
                    if path.name==locked_name:raise PermissionError('simulated control lock')
                    return real_unlink(path,*args,**kwargs)
                with patch.object(Path,'unlink',locked):result=module.uninstall(root)
                self.assertTrue(result['errors'])
                for name in ('uninstaller.py','installation_guard.py','Uninstall_HYBRIDIR.cmd',module.RECEIPT):
                    self.assertTrue((root/name).is_file(),name)
                retry_spec=importlib.util.spec_from_file_location('retry_uninstall',root/'uninstaller.py')
                retry=importlib.util.module_from_spec(retry_spec);retry_spec.loader.exec_module(retry)
                self.assertFalse(retry.uninstall(root)['folder_remains'])

    @unittest.skipUnless(os.name=='nt','Windows shortcut')
    def test_shortcut_only_if_recorded_and_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'app';self.setup_app(root)
            desktop=Path(td)/'desktop';desktop.mkdir();link=desktop/'HYBRID IR.lnk';link.write_bytes(b'owned-link')
            receipt=root/module.RECEIPT;data=json.loads(receipt.read_text())
            data['shortcut']=dict(path=str(link),sha256=module.digest(link));receipt.write_text(json.dumps(data))
            with patch.object(module,'desktop_path',return_value=desktop):module.uninstall(root)
            self.assertFalse(link.exists())

    def test_symlink_not_followed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'app';self.setup_app(root)
            outside=Path(td)/'outside';outside.mkdir();(outside/'keep').write_bytes(b'personal')
            try:(root/'linked').symlink_to(outside,target_is_directory=True)
            except OSError:self.skipTest('Symlink permission unavailable')
            module.uninstall(root)
            self.assertEqual((outside/'keep').read_bytes(),b'personal')
            self.assertTrue((root/'linked').is_symlink())

    @unittest.skipUnless(os.name=='nt','Windows junction')
    def test_junction_not_followed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'app';self.setup_app(root)
            outside=Path(td)/'outside';outside.mkdir();(outside/'keep').write_bytes(b'personal')
            script='New-Item -ItemType Junction -Path $env:HYBRID_TEST_JUNCTION -Target $env:HYBRID_TEST_TARGET | Out-Null'
            module.subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',
                module.base64.b64encode(script.encode('utf-16le')).decode('ascii')],
                env={**os.environ,'HYBRID_TEST_JUNCTION':str(root/'linked'),'HYBRID_TEST_TARGET':str(outside)},
                capture_output=True,check=True,timeout=30,creationflags=module.subprocess.CREATE_NO_WINDOW)
            self.assertTrue((root/'linked').is_junction())
            module.uninstall(root)
            self.assertEqual((outside/'keep').read_bytes(),b'personal')
            self.assertTrue((root/'linked').is_junction())

    @unittest.skipUnless(os.name=='nt','Windows junction')
    def test_appdata_ancestor_junction_preserves_shared_settings(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'app';self.setup_app(root)
            outside=Path(td)/'real';outside.mkdir()
            settings=outside/'Roaming/IRBQ_Lab/settings.json';settings.parent.mkdir(parents=True);settings.write_text('keep')
            linked=Path(td)/'linked'
            script='New-Item -ItemType Junction -Path $env:HYBRID_TEST_JUNCTION -Target $env:HYBRID_TEST_TARGET | Out-Null'
            module.subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',
                module.base64.b64encode(script.encode('utf-16le')).decode('ascii')],
                env={**os.environ,'HYBRID_TEST_JUNCTION':str(linked),'HYBRID_TEST_TARGET':str(outside)},
                capture_output=True,check=True,timeout=30,creationflags=module.subprocess.CREATE_NO_WINDOW)
            with patch.dict(os.environ,{'APPDATA':str(linked/'Roaming'),'IRBQ_SETTINGS_PATH':''}):
                result=module.uninstall(root,remove_preferences=True)
            self.assertEqual(settings.read_text(),'keep')
            self.assertIn('Linked preferences file',result['preserved'])

if __name__=='__main__':unittest.main()
