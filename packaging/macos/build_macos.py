"""Build a native preview from a validated public mirror, without publishing it."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile


# ARM64 SciPy's macosx_12_0 wheel actually declares 12.3 in Mach-O.
COMPAT_MINIMUM = '12.3'


def run(args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def build(source: Path, output: Path, revision: str, profile: str = 'standard'):
    if sys.platform!='darwin' or platform.machine() not in ('arm64','x86_64'):
        raise RuntimeError('Build on a native Apple Silicon or Intel macOS runner')
    if profile not in ('standard', 'compat12'):
        raise ValueError('Unknown macOS packaging profile')
    source=source.resolve();output=output.resolve()
    if not re.fullmatch(r'[0-9a-f]{40}',revision):raise ValueError('Use the exact committed source revision')
    if output.exists():raise FileExistsError('Choose a new build output directory')
    manifest=json.loads((source/'PUBLICATION_MANIFEST.json').read_text())
    if manifest['schema']!='hybridir-publication/1':raise ValueError('Not a reviewed public source tree')
    for entry in manifest['files']:
        p=source/entry['path']
        if not p.resolve().is_relative_to(source) or p.is_symlink():raise ValueError('Unsafe source path')
        if hashlib.sha256(p.read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Source checksum mismatch: '+entry['path'])
    version=json.loads((source/'release.json').read_text())['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Invalid version')
    arch=platform.machine()
    minimum = COMPAT_MINIMUM if profile == 'compat12' else '15.0'
    wheel_records = None
    if profile == 'compat12':
        from compat_profile import verify_environment
        wheel_records = verify_environment(source, arch)
    dependencies={d.metadata['Name']:d.version for d in importlib.metadata.distributions() if d.metadata.get('Name')}
    metadata=dict(schema='hybridir-macos-build/1',version=version,channel='macos-compat-preview' if profile == 'compat12' else 'macos-preview',
        architecture=arch,minimum_macos=minimum,tested_macos=platform.mac_ver()[0],
        source_revision=revision,public_manifest_sha256=hashlib.sha256((source/'PUBLICATION_MANIFEST.json').read_bytes()).hexdigest(),
        python=platform.python_version(),dependencies=dependencies,
        signing='ad-hoc',notarized=False,pedal_test=False)
    metadata['packaging_profile'] = profile
    if wheel_records is not None:
        metadata.update(compatibility_wheels=wheel_records, primary_target='13', secondary_target='12.3+',
                        old_os_runtime_validation='pending: test these exact bytes on macOS 13 and 12',
                        compatibility_basis='Mach-O load-command audit; not proof of old-OS API availability')
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='hybridir-macos-build-') as tmp:
        scratch=Path(tmp)
        info=scratch/'MACOS_BUILD.json';info.write_text(json.dumps(metadata,indent=2)+'\n')
        from PIL import Image
        icon=scratch/'HYBRIDIR.icns'
        with Image.open(source/'assets/zoom-ms70cdr.ico') as im:
            im.convert('RGBA').resize((1024,1024),Image.Resampling.LANCZOS).save(icon,format='ICNS')
        env=dict(os.environ,HYBRIDIR_PUBLIC_ROOT=str(source),HYBRIDIR_BUILD_METADATA=str(info),HYBRIDIR_MAC_ICON=str(icon),
                 PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
        env['MACOSX_DEPLOYMENT_TARGET'] = minimum
        run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',scratch/'dist',
             '--workpath',scratch/'build',source/'packaging/macos/HYBRIDIR.spec'],env=env,cwd=scratch)
        app=scratch/'dist/HYBRID IR.app'
        run(['codesign','--verify','--deep','--strict',app])
        from audit_macho import audit
        deployment = audit(app, minimum, arch)
        audit_path = output/'MACOS_DEPLOYMENT.json'
        audit_path.write_text(json.dumps(deployment, indent=2)+'\n', encoding='utf-8')
        if not deployment['success']:
            raise RuntimeError('macOS deployment audit failed: '+str(deployment['errors']))
        suffix = '-compat12-preview' if profile == 'compat12' else '-preview'
        title=f'HYBRID-IR-{version}-macOS-{arch}{suffix}'
        package=output/title;package.mkdir()
        run(['ditto',app,package/app.name])
        guide = source/('packaging/macos/compat' if profile == 'compat12' else 'packaging/macos')
        shutil.copyfile(guide/'README.md',package/'README.md')
        if profile == 'compat12':
            shutil.copyfile(guide/'README.ru.md',package/'README.ru.md')
        shutil.copyfile(audit_path,package/'MACOS_DEPLOYMENT.json')
        shutil.copyfile(info,package/'MACOS_BUILD.json')
        run([sys.executable,source/'packaging/macos/test_bundle.py','--app',package/app.name,'--report',output/'VALIDATION.json'])
        archive=output/(title+'.zip')
        run(['ditto','-c','-k','--sequesterRsrc','--keepParent',package,archive])
        sha=hashlib.sha256(archive.read_bytes()).hexdigest()
        (output/(archive.name+'.sha256')).write_text(sha+'  '+archive.name+'\n')
        (output/'MACOS_BUILD.json').write_text(json.dumps(metadata,indent=2)+'\n')
        print(archive)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--revision',required=True)
    p.add_argument('--profile', choices=('standard','compat12'), default='standard')
    args=p.parse_args();build(args.source,args.out,args.revision,args.profile)
