"""Relocate and launch the real .app with no developer Python on PATH."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import traceback


def inventory(root):
    return {p.relative_to(root).as_posix():('link:'+os.readlink(p) if p.is_symlink() else hashlib.sha256(p.read_bytes()).hexdigest())
            for p in root.rglob('*') if p.is_symlink() or p.is_file()}


def check(app, report):
    result={'success':False,'source_app':app.name,'notarized':False,'quarantine_gate_test':False}
    try:
        with tempfile.TemporaryDirectory(prefix='hybridir-bundle-test-') as tmp:
            root=Path(tmp);relocated=root/'Moved application [test] Проба'/'HYBRID IR.app';relocated.parent.mkdir()
            subprocess.run(['ditto',str(app),str(relocated)],check=True)
            for name in ('Python-3.14.6.txt','Python-3.14.6-incorporated.txt','Tcl-9.0.3.txt','Tk-9.0.3.txt'):
                if not (relocated/'Contents/Resources/licenses/macos'/name).is_file():
                    raise AssertionError('Missing bundled runtime notice: '+name)
            before=inventory(relocated)
            try:
                for p in relocated.rglob('*'):
                    if not p.is_symlink():p.chmod(p.stat().st_mode & ~0o222)
                executable=relocated/'Contents/MacOS/HYBRID IR'
                env={k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','DYLD_')) and k not in ('VIRTUAL_ENV','IRBQ_SETTINGS_PATH','MPLCONFIGDIR','HYBRIDIR_MAC_CACHE')}
                env['PATH']='/usr/bin:/bin:/usr/sbin:/sbin'
                home=root/'home';home.mkdir();env['HOME']=str(home)
                def run_check(command, folder):
                    completed=subprocess.run(command,cwd=root,env=env,timeout=240)
                    p=root/folder/'report.json'
                    if p.exists():result[folder]=json.loads(p.read_text())
                    if completed.returncode or not result.get(folder,{}).get('success'):
                        raise AssertionError('Bundle self-test failed: '+json.dumps(result.get(folder)))
                    if not result[folder].get('frozen'):raise AssertionError('Not a frozen application')
                run_check([str(executable),'--self-test',str(root/'direct')], 'direct')
                subprocess.run([str(executable),'--check-defaults',str(root/'direct/settings.json')],cwd=root,env=env,check=True,timeout=45)
                run_check(['open','-W','-n',str(relocated),'--args','--self-test',str(root/'finder')], 'finder')
                if inventory(relocated)!=before:raise AssertionError('Application bundle changed during launch')
                subprocess.run(['codesign','--verify','--deep','--strict',str(relocated)],check=True)
                result.update(success=True,defaults_fresh_process=True,relocated_unicode_path=True,
                              no_developer_python_on_path=True,bundle_unchanged=True,signature_verification=True)
            finally:
                for p in relocated.rglob('*'):
                    if not p.is_symlink():p.chmod(p.stat().st_mode | 0o200)
    except Exception:
        result['error']=traceback.format_exc()
        raise
    finally:
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--app',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    args=p.parse_args();check(args.app.resolve(),args.report.resolve())
