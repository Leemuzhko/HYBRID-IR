"""Update transaction tests: real temporary files, mocked pip/venv only."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from tests.test_installation import installer, installer_path

updater = installer.helper('updater')
guard = installer.helper('installation_guard')


@unittest.skipUnless(os.name == 'nt', 'Windows installer')
class TestUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hybrid update ' тест ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        for name in ('installer.py', 'uninstaller.py', 'installation_guard.py', 'updater.py', 'launch.py'):
            (self.source / name).write_bytes(installer_path.with_name(name).read_bytes())
        (self.source / 'requirements-zoom-lock.txt').write_text('')
        (self.source / 'program.txt').write_text('version one')
        self.manifest()
        self.destination = self.root / 'installed'
        def create(_self, path):
            path = Path(path);path.mkdir()
            (path / 'owned.txt').write_text('private environment: ' + str(path))
        self.addCleanup(patch.stopall)
        patch.object(installer.venv.EnvBuilder, 'create', create).start()
        patch.object(installer.subprocess, 'run').start()
        patch.object(updater, 'assert_not_running').start()
        installer.install(self.source, self.destination, full=False)
        (self.source / 'program.txt').write_text('version two')
        self.manifest()

    def manifest(self):
        entries = [dict(path=p.relative_to(self.source).as_posix(), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                   for p in self.source.rglob('*') if p.is_file() and p.name != 'PUBLICATION_MANIFEST.json']
        (self.source / 'PUBLICATION_MANIFEST.json').write_text(json.dumps(
            dict(schema='hybridir-publication/1', source_revision='fixture', files=entries)))

    def update(self, install=None):
        return updater.update(self.source, self.destination, install or installer.install, installer.checked_payload)

    def test_different_flavor_or_channel_is_rejected_before_staging(self):
        for flavor, channel in (('standalone','stable'),('lite','development')):
            with self.subTest(flavor=flavor,channel=channel):
                (self.source/'distribution.json').write_text(json.dumps(dict(
                    schema='hybridir-distribution/1',flavor=flavor,channel=channel)))
                self.manifest()
                before=updater.snapshot(self.destination)
                with self.assertRaisesRegex(ValueError,'separate folder'):
                    self.update()
                self.assertEqual(updater.snapshot(self.destination),before)

    def test_success_preserves_personal_modified_and_receipt_ownership(self):
        personal = self.destination / 'my IRs/кабінет.wav'
        personal.parent.mkdir();personal.write_bytes(b'personal IR')
        (self.destination / 'program.txt').write_text('local modification')
        result = self.update()
        self.assertEqual((self.destination / 'program.txt').read_text(), 'version two')
        self.assertEqual(personal.read_bytes(), b'personal IR')
        self.assertEqual((result['backup'] / 'program.txt').read_text(), 'local modification')
        self.assertIn('program.txt', result['modified'])
        receipt = json.loads((self.destination / 'uninstall-receipt.json').read_text())
        self.assertNotIn('my IRs/кабінет.wav', [e['path'] for e in receipt['files']])
        self.assertIn(str(self.destination / '.venv'), (self.destination / '.venv/owned.txt').read_text())
        self.assertFalse((self.root / 'installed.update.json').exists())
        result_uninstall = installer.helper('uninstaller').uninstall(self.destination)
        self.assertFalse(result_uninstall['errors'])
        self.assertEqual(personal.read_bytes(), b'personal IR')
        self.assertTrue(result['backup'].exists())

    def test_preparation_failure_leaves_old_tree_identical(self):
        before = updater.snapshot(self.destination)
        def fail(*args, **kwargs):
            raise RuntimeError('pip unavailable')
        with self.assertRaisesRegex(RuntimeError, 'old installation unchanged'):
            self.update(fail)
        self.assertEqual(before, updater.snapshot(self.destination))

    def test_final_install_failure_restores_old_tree(self):
        before = updater.snapshot(self.destination)
        def fail_final(source, destination, *args, **kwargs):
            if destination == self.destination:
                destination.mkdir();(destination / 'partial.txt').write_text('failed')
                raise RuntimeError('final validation failed')
            return installer.install(source, destination, *args, **kwargs)
        with self.assertRaisesRegex(RuntimeError, 'old installation restored'):
            self.update(fail_final)
        self.assertEqual(before, updater.snapshot(self.destination))
        self.assertTrue(list(self.root.glob('installed.failed-*/partial.txt')))

    def test_rollback_blocked_preserves_backup_and_journal(self):
        original = updater.rename_tree
        def rename(source, target):
            if '.backup-' in source.name:
                raise PermissionError('locked rollback')
            return original(source, target)
        def fail_final(source, destination, *args, **kwargs):
            if destination == self.destination:
                raise RuntimeError('final validation failed')
            return installer.install(source, destination, *args, **kwargs)
        with patch.object(updater, 'rename_tree', side_effect=rename):
            with self.assertRaisesRegex(RuntimeError, 'Automatic rollback blocked'):
                self.update(fail_final)
        journal = self.root / 'installed.update.json'
        self.assertTrue(journal.exists())
        backup = Path(json.loads(journal.read_text())['backup'])
        self.assertEqual((backup / 'program.txt').read_text(), 'version one')
        with self.assertRaisesRegex(ValueError, 'Interrupted update'):
            installer.install(self.source, self.destination, full=False)

    def test_locked_old_folder_never_replaced(self):
        before = updater.snapshot(self.destination)
        with patch.object(updater, 'rename_tree', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):self.update()
        self.assertEqual(before, updater.snapshot(self.destination))
        self.assertFalse((self.root / 'installed.update.json').exists())

    def test_personal_collision_rejected_before_install(self):
        (self.destination / 'personal.txt').write_text('keep')
        (self.source / 'personal.txt').write_text('new application file');self.manifest()
        with self.assertRaisesRegex(ValueError, 'Personal file conflicts'):self.update()
        self.assertEqual((self.destination / 'personal.txt').read_text(), 'keep')
        self.assertFalse(list(self.root.glob('installed.staging-*')))

    def test_old_app_owned_obsolete_file_is_backup_only(self):
        (self.source / 'program.txt').unlink();self.manifest()
        result = self.update()
        self.assertFalse((self.destination / 'program.txt').exists())
        self.assertTrue((result['backup'] / 'program.txt').exists())

    def test_legacy_receipt_and_tampered_payload_rejected(self):
        (self.source / 'program.txt').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'Damaged'):self.update()
        self.manifest()
        (self.destination / 'uninstall-receipt.json').unlink()
        with self.assertRaisesRegex(ValueError, 'No uninstall receipt'):self.update()

    def test_same_root_and_incomplete_rejected(self):
        with self.assertRaisesRegex(ValueError, 'separate extracted archive'):
            updater.describe(self.destination, self.destination, installer.checked_payload)
        (self.destination / '.installation-incomplete').touch()
        with self.assertRaisesRegex(ValueError, 'Incomplete installation'):self.update()

    def test_concurrent_change_aborts_before_rename(self):
        def alter(source, destination, *args, **kwargs):
            result = installer.install(source, destination, *args, **kwargs)
            (self.destination / 'new-user-file.txt').write_text('keep')
            return result
        with self.assertRaisesRegex(RuntimeError, 'changed during preparation'):self.update(alter)
        self.assertEqual((self.destination / 'program.txt').read_text(), 'version one')
        self.assertTrue((self.destination / 'new-user-file.txt').exists())

    def test_change_at_rename_restores_new_personal_file(self):
        rename = updater.rename_tree
        def alter(source, target):
            if source == self.destination and '.backup-' in target.name:
                (source / 'last-second.wav').write_bytes(b'personal')
            return rename(source, target)
        with patch.object(updater, 'rename_tree', side_effect=alter):
            with self.assertRaisesRegex(RuntimeError, 'old installation restored'):self.update()
        self.assertEqual((self.destination / 'last-second.wav').read_bytes(), b'personal')
        self.assertEqual((self.destination / 'program.txt').read_text(), 'version one')

    def test_browsing_legacy_folder_does_not_nest_new_install(self):
        (self.destination / 'uninstall-receipt.json').unlink()
        self.assertEqual(installer.browsed_destination(self.destination), self.destination)
        with self.assertRaisesRegex(ValueError, 'No uninstall receipt'):
            updater.describe(self.source, installer.browsed_destination(self.destination), installer.checked_payload)
        empty = self.root / 'empty';empty.mkdir()
        self.assertEqual(installer.browsed_destination(empty), empty / 'HYBRIDIR')

    def test_shortcut_receipt_failure_removes_only_new_link(self):
        link = self.root / 'HYBRID IR.lnk'
        def create(_destination):
            link.write_bytes(b'new shortcut')
            return dict(path=str(link), sha256=hashlib.sha256(link.read_bytes()).hexdigest())
        real_record = updater.atomic_record
        def record(path, data):
            if data.get('shortcut'):raise PermissionError('receipt locked')
            real_record(path, data)
        original_helper = updater.helper
        from types import SimpleNamespace
        def helper(name):
            return SimpleNamespace(create_desktop_shortcut=create) if name == 'installer' else original_helper(name)
        progress = []
        with patch.object(updater, 'helper', side_effect=helper),patch.object(updater, 'atomic_record', side_effect=record):
            updater.update(self.source, self.destination, installer.install, installer.checked_payload,
                           progress.append, desktop_shortcut=True)
        self.assertFalse(link.exists())
        self.assertTrue(any('unrecorded shortcut removed' in message for message in progress))
        self.assertIsNone(json.loads((self.destination / 'uninstall-receipt.json').read_text()).get('shortcut'))

    def test_launch_update_uninstall_mutex(self):
        with guard.installation_lock(self.destination):
            with self.assertRaisesRegex(ValueError, 'running'):self.update()
            with self.assertRaisesRegex(ValueError, 'running'):
                installer.helper('uninstaller').uninstall(self.destination)
        with guard.installation_lock(self.destination):pass

    def test_journal_blocks_launch_and_uninstall(self):
        (self.root / 'installed.update.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'interrupted update'):
            with guard.installation_lock(self.destination):pass
        with self.assertRaisesRegex(ValueError, 'interrupted update'):
            installer.helper('uninstaller').uninstall(self.destination)

    def test_shortcut_ownership_preserved(self):
        path = self.destination / 'uninstall-receipt.json'
        record = json.loads(path.read_text())
        record['shortcut'] = dict(path=str(self.root / 'HYBRID IR.lnk'), sha256='a'*64)
        path.write_text(json.dumps(record))
        self.update()
        self.assertEqual(json.loads(path.read_text())['shortcut'], record['shortcut'])

    def test_developer_settings_and_runtime_donors_are_reused(self):
        settings = self.destination / 'installation.json'
        data = json.loads(settings.read_text());data.update(zdl_enabled=True, ti_root='fixture compiler')
        settings.write_text(json.dumps(data))
        calls = []
        def capture(source, destination, ti, donor, full, progress, **kwargs):
            calls.append((destination, ti, Path(donor), full))
            return installer.install(source, destination, full=False, **kwargs)
        result = self.update(capture)
        self.assertEqual(calls[0][1:], ('fixture compiler', self.destination / 'hybridir_sdk', True))
        self.assertEqual(calls[1][1:], ('fixture compiler', result['backup'] / 'hybridir_sdk', True))


@unittest.skipUnless(os.name == 'nt', 'Windows lifecycle detection')
class TestWindowsUpdateGuard(unittest.TestCase):
    def test_relative_legacy_launcher_detected(self):
        with tempfile.TemporaryDirectory(prefix='hybrid relative ') as td:
            root = Path(td)
            (root / 'launch.py').write_text('import time; time.sleep(30)')
            child = subprocess.Popen([sys.executable, 'launch.py'], cwd=root,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                with self.assertRaises(subprocess.CalledProcessError) as error:updater.assert_not_running(root)
                self.assertEqual(error.exception.returncode, 23)
            finally:
                child.terminate();child.wait(timeout=10)
            updater.assert_not_running(root)

    def test_legacy_running_process_detected(self):
        with tempfile.TemporaryDirectory(prefix='hybrid process ') as td:
            root = Path(td)
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)', str(root/'launch.py')],
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                with self.assertRaises(subprocess.CalledProcessError) as error:
                    updater.assert_not_running(root)
                self.assertEqual(error.exception.returncode, 23)
            finally:
                child.terminate();child.wait(timeout=10)
            updater.assert_not_running(root)

    def test_junction_path_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td);target=root/'real';target.mkdir();linked=root/'linked'
            script='New-Item -ItemType Junction -Path $env:HYBRID_LINK -Target $env:HYBRID_TARGET | Out-Null'
            subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',
                updater.base64.b64encode(script.encode('utf-16le')).decode('ascii')],
                env={**os.environ,'HYBRID_LINK':str(linked),'HYBRID_TARGET':str(target)},
                check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
            with self.assertRaisesRegex(ValueError,'Linked'):updater.safe_root(linked/'app')
            with self.assertRaisesRegex(ValueError,'link or junction'):updater.snapshot(root)


if __name__ == '__main__':unittest.main()
