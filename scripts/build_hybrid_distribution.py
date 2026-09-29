"""Build separate Lite / offline Standalone archives from one Git revision.

Run in a reviewed public/development repository, not the parent research tree.
No device access, DSP compilation, source ZIP masquerading as an installer,
or copying of an existing developer virtual environment.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def destination_for(name):
    """Allow application/runtime inputs; exclude tests, research and user data."""
    p = Path(name)
    if name.startswith('hybridir_sdk/templates/') and p.name not in {'HIR3A.ZDL','HIR3A.template.json'}:
        return None
    if any(part in {'.git', '.venv', '__pycache__', 'tests', 'inputs', 'examples', 'results'} for part in p.parts):
        return None
    helpers = {'installer.py', 'launch.py', 'updater.py', 'uninstaller.py',
               'installation_guard.py', 'distribution_runtime.py', 'standalone_uninstall.ps1',
               'Install_HYBRIDIR.cmd', 'THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.uk.md',
               'UPSTREAM_PROVENANCE.json'}
    if name in helpers or name in {'LICENSE', 'requirements-zoom-lock.txt'}:
        return name
    if name.startswith('packaging/hybridir/'):
        tail = name.removeprefix('packaging/hybridir/')
        if tail in helpers or tail.startswith('licenses/'):
            return tail
        if tail == 'zoom-ms70cdr.ico':
            return 'assets/zoom-ms70cdr.ico'
    if name.startswith(('licenses/', 'assets/')):
        return name
    if name.startswith('irbq_lab/irbq/') and p.suffix in {'.py', '.json'}:
        return name
    if name in ('irbq_lab/run.py', 'irbq_lab/LICENSE.txt'):
        return name
    if name.startswith('hybridir_sdk/') and p.suffix.lower() in {'.py', '.c', '.h', '.json', '.zdl', '.png', '.rle'}:
        return name
    if name.startswith('docs/hybridir_user/'):
        return name.replace('docs/hybridir_user/', 'docs/', 1)
    if re.match(r'docs/(en|ru|uk)/', name):
        return name
    return None


def channel_for_markers(markers):
    expected={'PUBLICATION_MANIFEST.json':('stable','hybridir-publication/1'),
              'DEVELOPMENT_MANIFEST.json':('development','hybridir-development-snapshot/1')}
    if len(markers)!=1 or next(iter(markers)) not in expected:
        raise ValueError('Exactly one bounded repository marker is required')
    name=next(iter(markers));channel,schema=expected[name]
    if markers[name].get('schema')!=schema:
        raise ValueError('Invalid source marker schema')
    return channel


def source_listing(repo, revision):
    """Resolve a bounded project at the root OR a monorepo subdirectory."""
    commit=subprocess.check_output(['git','-C',str(repo),'rev-parse',revision+'^{commit}'],text=True).strip()
    prefix=subprocess.check_output(['git','-C',str(repo),'rev-parse','--show-prefix'],text=True).strip()
    tree=commit+':'+prefix.rstrip('/') if prefix else commit
    names=subprocess.check_output(['git','-C',str(repo),'ls-tree','--full-tree','-r','--name-only',tree],text=True).splitlines()
    return commit,prefix,names


def source_identity(repo, revision):
    commit,prefix,names=source_listing(repo,revision)
    markers={name:json.loads(subprocess.check_output(['git','-C',str(repo),'show',commit+':'+prefix+name]))
             for name in ('PUBLICATION_MANIFEST.json','DEVELOPMENT_MANIFEST.json') if name in names}
    return commit,channel_for_markers(markers)


def runtime_requirements(raw):
    return b'\n'.join(line for line in raw.splitlines() if not line.startswith(b'ziglang=='))+b'\n'


def export_revision(repo, revision, output):
    revision,prefix,names=source_listing(repo,revision)
    source_identity(repo,revision)  # Fail closed on missing/ambiguous channel markers.
    seen = set()
    for name in names:
        target_name = destination_for(name)
        if target_name is None:
            continue
        if target_name.casefold() in seen:
            raise ValueError('Duplicate payload destination: '+target_name)
        seen.add(target_name.casefold())
        raw = subprocess.check_output(['git', '-C', str(repo), 'show', revision+':'+prefix+name])
        if raw.startswith(b'version https://git-lfs.github.com/spec/'):
            raise ValueError('Materialize and explicitly review LFS before release: '+name)
        if name == 'requirements-zoom-lock.txt':
            # Zig only compiles host-test fixtures; it is not used by Trainer,
            # the template patcher, or the separate TI build path.
            raw=runtime_requirements(raw)
        path = output / target_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    required = ('installer.py', 'distribution_runtime.py', 'uninstaller.py', 'launch.py',
                'irbq_lab/run.py', 'requirements-zoom-lock.txt', 'assets/zoom-ms70cdr.ico',
                'irbq_lab/irbq/bank_prepare.py', 'irbq_lab/irbq/source_audio.py',
                'irbq_lab/irbq/template_profile.py', 'irbq_lab/irbq/template_patch.py',
                'hybridir_sdk/templates/HIR3A.ZDL', 'hybridir_sdk/templates/HIR3A.template.json')
    if any(not (output/name).is_file() for name in required):
        raise ValueError('Incomplete application payload')
    return revision


def bundle_python(output):
    if os.name != 'nt' or sys.version_info[:2] != (3, 14) or sys.maxsize <= 2**32:
        raise ValueError('Standalone build requires official Windows x64 CPython 3.14 with Tk')
    base = Path(sys.base_prefix)
    runtime = output / 'runtime'
    runtime.mkdir()
    for name in ('python.exe', 'pythonw.exe', 'python3.dll', 'python314.dll',
                 'vcruntime140.dll', 'vcruntime140_1.dll', 'LICENSE.txt'):
        shutil.copyfile(base/name, runtime/name)
    for name in ('Lib', 'DLLs', 'tcl'):
        shutil.copytree(base/name, runtime/name,
                        ignore=shutil.ignore_patterns('site-packages', '__pycache__', '*.pyc', 'test', 'tests', 'idlelib', 'ensurepip', 'sitecustomize.py', 'usercustomize.py', '*.pth'))
    (output/'RUNTIME_PROVENANCE.json').write_text(json.dumps(dict(
        schema='hybridir-runtime/1', python_version=sys.version,
        source='Windows CPython base runtime with Tcl/Tk; dependencies resolved from requirements-zoom-lock.txt',
        python_sha256=digest(runtime/'python.exe'),
        dependency_lock_sha256=digest(output/'requirements-zoom-lock.txt'),
        licenses='runtime/LICENSE.txt, runtime/tcl, runtime/Lib/site-packages/*dist-info'), indent=2), encoding='utf-8')
    # Resolve dependencies afresh from the lock, never copy an arbitrary venv.
    subprocess.run([sys.executable, '-m', 'pip', '--isolated', 'install', '--index-url',
                    'https://pypi.org/simple', '--only-binary=:all:', '--no-compile',
                    '--target', str(runtime/'Lib/site-packages'),
                    '-r', str(output/'requirements-zoom-lock.txt')], check=True)
    # pip-generated console launchers embed the build machine's interpreter path.
    # They are not used by the GUI and must not ship as broken entry points.
    launchers = runtime/'Lib/site-packages/bin'
    if launchers.exists():
        for entry in launchers.iterdir():
            if not entry.is_file() or entry.is_symlink():
                raise ValueError('Unexpected dependency console launcher')
            entry.unlink()
        launchers.rmdir()
    # Explicit paths prevent registry, PYTHONPATH and user site-packages leakage.
    (runtime/'python314._pth').write_text(
        'Lib\nDLLs\nLib/site-packages\n..\n../irbq_lab\n../hybridir_sdk\nimport site\n', encoding='utf-8')
    env = {**os.environ, 'PATH':str(Path(os.environ['SystemRoot'])/'System32'),
           'PYTHONHOME':'invalid-isolation-probe', 'PYTHONPATH':'invalid-isolation-probe'}
    subprocess.run([str(runtime/'python.exe'), '-B', '-c',
                    'import tkinter,numpy,scipy,matplotlib,soundfile,PIL; '
                    'r=tkinter.Tk(); r.withdraw(); r.update(); r.destroy()'],
                   env=env, cwd=output, check=True, timeout=120)


def build(repo, revision, out, flavor, channel, version):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.\-]{0,60}', version):
        raise ValueError('Unsafe version')
    revision, expected_channel=source_identity(repo, revision)
    if channel is not None and channel!=expected_channel:
        raise ValueError('Channel does not match the committed source marker')
    channel=expected_channel
    if flavor not in ('lite', 'standalone'):
        raise ValueError('Unsupported distribution')
    name = f'HYBRID-IR-{version}-Windows-x64-{flavor.title()}'
    folder = out / name
    folder.mkdir(parents=True, exist_ok=False)
    commit = export_revision(repo, revision, folder)
    (folder/'distribution.json').write_text(json.dumps(dict(
        schema='hybridir-distribution/1', flavor=flavor, channel=channel,
        version=version, source_revision=commit,
        excluded_test_dependencies=['ziglang']), indent=2), encoding='utf-8')
    if flavor == 'standalone':
        bundle_python(folder)
        (folder/'Install_HYBRIDIR.cmd').write_text(
            '@echo off\nsetlocal\ncd /d "%~dp0"\n"runtime\\python.exe" -B -X utf8 installer.py\nif errorlevel 1 pause\n', encoding='utf-8')
    (folder/'README.txt').write_text(
        f'HYBRID IR {version} / {channel} / {flavor}\n\n'
        'Extract the complete ZIP, then run Install_HYBRIDIR.cmd.\n'
        + ('Offline: Python and dependencies are included.\n' if flavor=='standalone'
           else 'Requires official 64-bit Python 3.14 with Tk and py launcher. Installation downloads dependencies.\n')
        + 'See docs/en/installation.md (ru and uk also available).\n'
        'Updates: use the same flavor/channel, close the app first. Backups are retained.\n'
        'To change flavor/channel, choose a separate installation folder.\n'
        'Uninstall: run Uninstall_HYBRIDIR.cmd in the installation folder.\n'
        'Your IRs, banks and projects are not deleted automatically.\n'
        'No TI compiler is required to patch existing templates. No new pedal validation is implied.\n', encoding='utf-8')
    for readme in ('README.md', 'README.ru.md', 'README.uk.md'):
        (folder/readme).write_text('# HYBRID IR\n\n[Installation](docs/en/installation.md) · [Русский](docs/ru/installation.md) · [Українська](docs/uk/installation.md)\n\n[Ready-made effects](https://github.com/Leemuzhko/Zoom-ZDL-FX/tree/main/zdl/)\n', encoding='utf-8')
    files = [dict(path=p.relative_to(folder).as_posix(), sha256=digest(p))
             for p in sorted(folder.rglob('*')) if p.is_file()]
    (folder/'PUBLICATION_MANIFEST.json').write_text(json.dumps(dict(
        schema='hybridir-publication/1', source_revision=commit, files=files), indent=2), encoding='utf-8')
    archive = out/(name+'.zip')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                bundle.write(path, name+'/'+path.relative_to(folder).as_posix())
    (out/(name+'.zip.sha256')).write_text(digest(archive)+'  '+archive.name+'\n', encoding='ascii')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--revision', default='HEAD')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--channel', choices=('stable', 'development'), help='Optional assertion; derived from the committed source marker')
    parser.add_argument('--flavor', choices=('lite', 'standalone', 'both'), default='both')
    args = parser.parse_args()
    for flavor in (('lite', 'standalone') if args.flavor=='both' else (args.flavor,)):
        print(build(args.repo.resolve(), args.revision, args.out.resolve(), flavor, args.channel, args.version))
