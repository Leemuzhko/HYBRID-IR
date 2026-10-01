"""Native system aliases are not permission to follow arbitrary user links."""
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from irbq import app_paths
from irbq.preferences import settings_path


class AppPaths(unittest.TestCase):
    def test_source_resource_root(self):
        self.assertTrue((app_paths.application_root()/'hybridir_sdk').is_dir())

    def test_frozen_resource_root(self):
        with patch.object(sys,'frozen',True,create=True), patch.object(sys,'_MEIPASS','/bundle/resources',create=True):
            self.assertEqual(app_paths.application_root(),Path('/bundle/resources'))

    def test_parent_traversal_rejected(self):
        with self.assertRaises(ValueError):app_paths.safe_output_directory(Path('workspace')/'..'/'outside')

    def test_plain_path_preserves_spelling(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(app_paths.safe_output_directory(tmp),Path(tmp))

    @unittest.skipIf(os.name=='nt','Native symlink test; Windows junction coverage is separate')
    def test_user_link_and_broken_link_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();outside=root/'outside';outside.mkdir()
            link=root/'link';link.symlink_to(outside,target_is_directory=True)
            broken=root/'broken';broken.symlink_to(root/'absent',target_is_directory=True)
            for path in (link/'export',broken/'export'):
                with self.subTest(path=path),self.assertRaises(ValueError):app_paths.safe_output_directory(path)
            self.assertEqual(list(outside.iterdir()),[])

    @unittest.skipUnless(sys.platform=='darwin','Requires real Apple system aliases')
    def test_real_system_aliases(self):
        for alias,target in app_paths._SYSTEM_ALIASES.items():
            path=Path(alias)
            if path.is_symlink():
                self.assertEqual(app_paths._system_alias(path),Path(target))
                self.assertEqual(app_paths.safe_output_directory(path/'new'),path/'new')

    @unittest.skipUnless(sys.platform=='darwin','Requires real Apple system aliases')
    def test_macos_alias_does_not_allow_user_link_below_it(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root=Path(tmp);outside=root/'outside';outside.mkdir()
            (root/'linked').symlink_to(outside,target_is_directory=True)
            with self.assertRaises(ValueError):app_paths.safe_output_directory(root/'linked'/'new')

    @unittest.skipUnless(sys.platform=='darwin','Uses POSIX root alias spellings')
    def test_modified_alias_or_non_root_owner_rejected(self):
        for owner,target in ((501,'private/var'),(0,'private/tmp'),(0,'/unexpected')):
            with self.subTest(owner=owner,target=target),patch.object(Path,'lstat',return_value=SimpleNamespace(st_uid=owner,st_mode=stat.S_IFLNK)),patch.object(os,'readlink',return_value=target):
                self.assertIsNone(app_paths._system_alias(Path('/var')))

    def test_mac_settings_outside_bundle(self):
        env={key:value for key,value in os.environ.items() if key!='IRBQ_SETTINGS_PATH'}
        with patch.dict(os.environ,env,clear=True),patch.object(sys,'platform','darwin'):
            self.assertEqual(settings_path(),Path.home()/'Library'/'Application Support'/'HYBRID IR'/'settings.json')

    def test_override_kept(self):
        with patch.dict(os.environ,{'IRBQ_SETTINGS_PATH':'custom-settings.json'}):
            self.assertEqual(settings_path(),Path('custom-settings.json'))


if __name__=='__main__':unittest.main()
