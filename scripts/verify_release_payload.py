"""Verify a built/installed application using its own Python and disposable user data."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile


def verify(root):
    root=root.resolve()
    metadata=json.loads((root/'distribution.json').read_text(encoding='utf-8'))
    templates=root/'hybridir_sdk/templates'
    assert {p.name for p in templates.iterdir() if p.is_file()}=={'HIR3A.ZDL','HIR3A.template.json'}
    for name in ('bank_prepare','source_audio','template_patch','template_profile'):
        assert (root/f'irbq_lab/irbq/{name}.py').is_file(),name
    sys.path.insert(0,str(root/'irbq_lab'))
    sys.path.insert(0,str(root))
    from irbq import __version__
    assert __version__==metadata['version']
    from irbq.gui import App,NORM_NAMES
    from irbq.dsp import Model,PrepConfig,prepare,response_normalization_power
    from irbq.template_profile import load_package
    from irbq.template_patch import patch_project
    from irbq.zoom_bank import BankProject,Slot
    from PIL import Image
    import numpy as np
    package=load_package(templates/'HIR3A.template.json')
    assert package.profile['sha256']=='14f605e66ea0ca24a1bd0b0873cb15b8dbaf900290ffe78f9f6cb60c99b0f9d4'
    modes=('k_weighted','k_band','k_pink','k_pink_band')
    with tempfile.TemporaryDirectory(prefix='hybridir-release-check-') as td:
        folder=Path(td);os.environ['IRBQ_SETTINGS_PATH']=str(folder/'settings.json')
        h=np.r_[.7,.3,-.1,np.zeros(61)]
        for mode in modes:
            assert mode in NORM_NAMES.values()
            out,_,_=prepare(h,44100,PrepConfig(minimum_phase=False,trim_start=False,normalization=mode,level_db=-3))
            H=np.fft.rfft(out,65536);f=np.fft.rfftfreq(65536,1/44100)
            assert abs(10*np.log10(response_normalization_power(H,f,44100,mode))+3)<1e-8
        app=App();app.withdraw()
        try:
            assert Path(app.zoom_panel.template_path).name=='HIR3A.template.json'
            assert app.zoom_panel.estimate()['active_slots']==0
            app._sync_prep_config(PrepConfig(normalization='k_pink_band',level_db=-3,minimum_phase=False))
            app.save_prep_defaults()
            assert json.loads((folder/'settings.json').read_text(encoding='utf-8'))['prep_defaults']['normalization']=='k_pink_band'
        finally:app.player.close();app.destroy()
        app=App();app.withdraw()
        try:
            assert app.read_prep().normalization=='k_pink_band'
            assert app.read_prep().level_db==-3
        finally:app.player.close();app.destroy()
        # Check a fresh interpreter too, not just a second window in the same process.
        code='import sys;sys.path.insert(0,sys.argv[1]);from irbq.preferences import load_preferences;assert load_preferences().prep_defaults["normalization"]=="k_pink_band"'
        subprocess.run([sys.executable,'-B','-c',code,str(root/'irbq_lab')],check=True,timeout=30)
        p=BankProject(name='RELEASE TEST',filename='RELTEST',fxid=901,slots=[Slot('UNIT',Model(44100,h,[]))])
        path,receipt=patch_project(p,folder/'export',profile_path=package.profile_path,allow_experimental=True)
        assert path.suffix.upper()=='.ZDL'  # physical extension is case-insensitive; device metadata is uppercase
        assert hashlib.sha256(path.read_bytes()).hexdigest()==receipt['sha256']
        meta=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
        assert meta['inDeviceFileName']=='RELTEST.ZDL'
        with Image.open(path.with_suffix('.png')) as im:assert im.mode=='RGBA' and im.size==(128,96)
        empty=BankProject()
        try:patch_project(empty,folder/'empty',profile_path=package.profile_path,allow_experimental=True)
        except ValueError:pass
        else:raise AssertionError('Empty export was accepted')
        assert not (folder/'empty').exists()
    report=dict(version=__version__,flavor=metadata['flavor'],channel=metadata['channel'],
                interpreter=sys.version,source_revision=metadata['source_revision'],
                k_modes=list(modes),defaults_restart=True,hir3a_export=True,
                empty_bank_guard=True,templates=['HIR3A.ZDL','HIR3A.template.json'],
                host_only=True,pedal_timing_test=False)
    print(json.dumps(report,indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    args=p.parse_args();verify(args.root)
