"""Launcher tests; simulated version checks are NOT actual Python-3.14 execution."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import bootstrap

class TestBootstrap(unittest.TestCase):
    def test_supported_versions_include_314(self):
        for minor in (11, 12, 13, 14):
            with self.subTest(minor=minor):
                bootstrap.check_runtime((3, minor), 2**63 - 1)

    def test_unsupported_versions(self):
        for version in ((3, 10), (3, 15), (2, 7)):
            with self.subTest(version=version):
                with self.assertRaises(RuntimeError):
                    bootstrap.check_runtime(version, 2**63 - 1)

    def test_reject_32_bit(self):
        with self.assertRaisesRegex(RuntimeError, '64-bit'):
            bootstrap.check_runtime((3, 14), 2**31 - 1)

    def test_windows_launcher_lists_314(self):
        cmd = (Path(bootstrap.__file__).parent / 'Start_IRBQ_Lab.cmd').read_text()
        self.assertIn('(3.14 3.13 3.12 3.11)', cmd)
        self.assertIn('exit /b %IRBQ_RESULT%', cmd)

    def test_simulated_314_reaches_application(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            exe.parent.mkdir(parents=True)
            exe.touch()
            with patch.object(bootstrap, 'HERE', root), \
                 patch.object(sys, 'version_info', (3, 14, 0)), \
                 patch.object(sys, 'argv', ['bootstrap.py', 'demo.irbq']), \
                 patch.object(bootstrap.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                 patch.object(bootstrap.subprocess, 'call', return_value=0) as launch:
                self.assertEqual(bootstrap.main(), 0)
                launch.assert_called_once_with([str(exe), str(root / 'run.py'), 'demo.irbq'], cwd=root)

if __name__ == '__main__':
    unittest.main()
