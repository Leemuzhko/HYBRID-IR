"""Isolated host tests; optional TI/private-evidence checks are reported separately."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
OPTIONAL={
    'test_zoom_build':'TI CGT and locally provisioned donor runtime fragments',
    'test_hybrid_card':'TI build and historical golden card/descriptor assertions',
    'test_hybrid_controls':'historical mapper_execution.json evidence outside source snapshot',
    'test_hybrid_runtime':'historical non-synthetic golden coefficient assertions',
}
if os.name!='nt':
    OPTIONAL.update(test_installation='Windows lifecycle gate',
                    test_uninstall='Windows lifecycle gate',test_update='Windows lifecycle gate')


def main():
    results=[]
    with tempfile.TemporaryDirectory(prefix='hir-host-tests-') as td:
        for path in sorted((ROOT/'irbq_lab/tests').glob('test_*.py')):
            if path.stem in OPTIONAL:
                print('EXCLUDED '+path.stem+': '+OPTIONAL[path.stem],flush=True)
                results.append(dict(suite=path.stem,excluded=OPTIONAL[path.stem]));continue
            env=dict(os.environ,PYTHONPATH=str(ROOT/'irbq_lab'),PYTHONFAULTHANDLER='1',PYTHONUTF8='1',
                     IRBQ_SETTINGS_PATH=str(Path(td)/(path.stem+'.json')),MPLCONFIGDIR=str(Path(td)/'matplotlib'))
            print('\nSUITE '+path.stem,flush=True)
            try:
                run=subprocess.run([sys.executable,'-B','-X','utf8','-m','unittest','discover','-s',str(path.parent),'-p',path.name,'-v'],
                                   cwd=ROOT/'irbq_lab',env=env,timeout=180)
                results.append(dict(suite=path.stem,returncode=run.returncode))
            except subprocess.TimeoutExpired:
                results.append(dict(suite=path.stem,returncode=124));print('SUITE TIMED OUT',flush=True)
    failed=[r['suite'] for r in results if r.get('returncode',0)!=0]
    print(json.dumps(dict(host_only=True,suites=results,failed=failed),indent=2),flush=True)
    print('Host checks only; no pedal or TI execution.',flush=True)
    return bool(failed)

if __name__=='__main__':sys.exit(main())
