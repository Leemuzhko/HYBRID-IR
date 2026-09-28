"""Real install/update/uninstall smoke using only disposable paths."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def smoke(source, work):
    source=source.resolve();work=work.resolve()
    work.mkdir(parents=True,exist_ok=False)
    installer=load(source/'installer.py','distribution_installer')
    delivery=installer.helper('distribution_runtime').metadata(source)
    target=work/'installed'
    installer.install(source,target,full=False,progress=print)
    personal=target/'personal-bank.txt';personal.write_text('preserve me')
    update=installer.helper('updater')
    result=update.update(source,target,installer.install,installer.checked_payload,print)
    assert personal.read_text()=='preserve me'
    assert (result['backup']/'personal-bank.txt').read_text()=='preserve me'
    receipt=json.loads((target/'uninstall-receipt.json').read_text())
    assert 'personal-bank.txt' not in {x['path'] for x in receipt['files']}
    if delivery['flavor']=='standalone':
        # Move a complete runtime and run with no Python on PATH and poisoned
        # Python environment variables. Do not pretend this is a pristine VM.
        relocated=work/'relocated runtime'
        shutil.copytree(target/'runtime',relocated/'runtime')
        for name in ('uninstaller.py','installation_guard.py'):
            shutil.copyfile(target/name,relocated/name)
        python=relocated/'runtime/python.exe'
        env={**os.environ,'PATH':str(Path(os.environ['SystemRoot'])/'System32'),
             'PYTHONHOME':'invalid-probe','PYTHONPATH':'invalid-probe'}
        code=('import tkinter,numpy,scipy,matplotlib,soundfile,PIL; '
              'r=tkinter.Tk(); r.withdraw(); r.update(); r.destroy(); '
              'from uninstaller import uninstall; '
              'import sys,json; result=uninstall(sys.argv[1]); '
              'print(json.dumps(result)); assert not result["errors"]')
    else:
        python=Path(sys.executable)
        env={**os.environ,'PYTHONPATH':str(source)}
        code='from uninstaller import uninstall; import sys; result=uninstall(sys.argv[1]); print(result); assert not result["errors"]'
    subprocess.run([str(python),'-B','-c',code,str(target)],env=env,cwd=work,check=True,timeout=180)
    assert personal.read_text()=='preserve me'
    assert not (target/'runtime').exists()
    assert not (target/'.venv').exists()
    report=dict(flavor=delivery['flavor'],channel=delivery['channel'],
                source_revision=delivery['source_revision'],install=True,update=True,
                uninstall=True,personal_preserved=True,pristine_vm=False,
                hardware_validation=False)
    (work/'smoke.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args();smoke(args.source,args.work)
