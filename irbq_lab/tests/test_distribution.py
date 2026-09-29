"""Delivery boundary tests; real Windows lifecycle is a separate gate."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tests.test_installation import installer


class TestDistribution(unittest.TestCase):
    def test_only_current_template_is_shipped(self):
        import runpy
        root=Path(__file__).resolve().parents[2]
        choose=runpy.run_path(str(root/'scripts/build_hybrid_distribution.py'))['destination_for']
        for name in ('HIR3A.ZDL','HIR3A.template.json'):
            self.assertEqual(choose('hybridir_sdk/templates/'+name),'hybridir_sdk/templates/'+name)
        for name in ('HVB4RBJ.zdl','IRDUAL4P.ZDL','HVB4REF.template.json'):
            self.assertIsNone(choose('hybridir_sdk/templates/'+name))

    def test_source_listing_respects_monorepo_boundary(self):
        import runpy
        import subprocess
        root=Path(__file__).resolve().parents[2]
        builder=runpy.run_path(str(root/'scripts/build_hybrid_distribution.py'))
        with tempfile.TemporaryDirectory() as td:
            repo=Path(td);project=repo/'HYBRID-IR';project.mkdir()
            (repo/'outside.txt').write_text('must not be exported')
            (project/'DEVELOPMENT_MANIFEST.json').write_text(json.dumps({'schema':'hybridir-development-snapshot/1'}))
            (project/'inside.py').write_text('pass')
            def git(*args):
                return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.STDOUT,text=True)
            git('init');git('add','.')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','fixture')
            commit,prefix,names=builder['source_listing'](project,'HEAD')
            self.assertEqual(prefix,'HYBRID-IR/')
            self.assertEqual(set(names),{'inside.py','DEVELOPMENT_MANIFEST.json'})
            self.assertEqual(builder['source_identity'](project,'HEAD'),(commit,'development'))
            with self.assertRaises(ValueError):builder['source_identity'](repo,'HEAD')

    def test_legacy_is_lite_stable(self):
        helper = installer.helper('distribution_runtime')
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(helper.metadata(td)['flavor'], 'lite')
            self.assertEqual(helper.interpreter(td), Path(td)/'.venv/Scripts/python.exe')

    def test_standalone_paths_and_invalid_metadata(self):
        helper = installer.helper('distribution_runtime')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root/'distribution.json'
            path.write_text(json.dumps(dict(schema='hybridir-distribution/1', flavor='standalone', channel='development')))
            self.assertEqual(helper.interpreter(root, True), root/'runtime/pythonw.exe')
            with patch.dict('os.environ', {'USERPROFILE':td}, clear=True):
                helper.configure_preferences(root)
                import os
                self.assertIn('HYBRIDIR-Development', os.environ['IRBQ_SETTINGS_PATH'])
            path.write_text('{}')
            with self.assertRaises(ValueError):helper.metadata(root)

    def test_standalone_install_never_creates_venv_or_runs_pip(self):
        import hashlib
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/'source';source.mkdir()
            target = Path(td)/'installed'
            for name in ('installer.py','uninstaller.py','installation_guard.py','launch.py'):
                (source/name).write_bytes(Path(installer.__file__).with_name(name).read_bytes())
            (source/'runtime').mkdir()
            (source/'runtime/python.exe').write_bytes(b'test-only')
            (source/'distribution.json').write_text(json.dumps(dict(schema='hybridir-distribution/1', flavor='standalone',channel='stable')))
            entries=[dict(path=p.relative_to(source).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in source.rglob('*') if p.is_file()]
            (source/'PUBLICATION_MANIFEST.json').write_text(json.dumps(dict(schema='hybridir-publication/1',files=entries)))
            with patch.object(installer.venv.EnvBuilder,'create',side_effect=AssertionError('offline')):
                with patch.object(installer.subprocess,'run') as run:
                    installer.install(source,target,full=False)
                    self.assertEqual(run.call_count,1)  # Only the installed GUI smoke.
                    self.assertEqual(Path(run.call_args.args[0][0]).resolve(),(target/'runtime/python.exe').resolve())
            self.assertIn('standalone_uninstall.ps1',(target/'Uninstall_HYBRIDIR.cmd').read_text())
            self.assertIn('runtime\\python.exe',(target/'Start_HYBRIDIR.cmd').read_text())

    def test_packaging_allowlist(self):
        root = Path(__file__).resolve().parents[2]
        path = root/'scripts/build_hybrid_distribution.py'
        spec=importlib.util.spec_from_file_location('distribution_builder',path)
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        for name in ('results/bank.wav','irbq_lab/tests/test_gui.py','docs/ZDL_HARDWARE_LIMITS_RU.md','.venv/secret.py','irbq_lab/examples/model.json'):
            self.assertIsNone(builder.destination_for(name))
        self.assertEqual(builder.destination_for('packaging/hybridir/installer.py'),'installer.py')
        self.assertEqual(builder.destination_for('docs/hybridir_user/ru/workflow.md'),'docs/ru/workflow.md')
        stable={'PUBLICATION_MANIFEST.json':{'schema':'hybridir-publication/1'}}
        dev={'DEVELOPMENT_MANIFEST.json':{'schema':'hybridir-development-snapshot/1'}}
        self.assertEqual(builder.channel_for_markers(stable),'stable')
        self.assertEqual(builder.channel_for_markers(dev),'development')
        for markers in ({},{**stable,**dev},{'PUBLICATION_MANIFEST.json':{'schema':'bad'}}):
            with self.assertRaises(ValueError):builder.channel_for_markers(markers)
        with tempfile.TemporaryDirectory() as td,patch.object(builder,'source_identity',return_value=('abc','development')):
            with self.assertRaisesRegex(ValueError,'Channel'):
                builder.build(Path(td),'HEAD',Path(td)/'out','lite','stable','1.0')
            self.assertFalse((Path(td)/'out').exists())
        self.assertEqual(builder.runtime_requirements(b'numpy==2.5.3\r\nziglang==0.16.0\r\n'),b'numpy==2.5.3\n')


if __name__=='__main__':unittest.main()
