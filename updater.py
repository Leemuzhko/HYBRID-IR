"""Receipt-based updates: preserve the old tree; rebuild venv at its final path.

No recursive deletes. Failed candidates and successful backups remain beside
the installation for inspection. Unowned files are never enrolled in receipts.
"""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def helper(name):
    spec = importlib.util.spec_from_file_location('hybrid_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_root(path):
    root = Path(path).absolute()
    if root == Path(root.anchor) or root == Path.home():
        raise ValueError('Unsafe installation folder')
    if any(p.is_symlink() or p.is_junction() for p in (root, *root.parents)):
        raise ValueError('Linked installation paths are not supported')
    return root


def snapshot(root):
    """Include empty directories; reject links rather than following them."""
    uninstaller = helper('uninstaller')
    result = {}
    for path in uninstaller.walk(root):
        if not uninstaller.plain_path(path, root):
            raise ValueError('Installation contains a link or junction: ' + str(path))
        relative = path.relative_to(root).as_posix()
        result[relative] = uninstaller.digest(path) if path.is_file() else None
    return result


def revision(root):
    path = Path(root) / 'PUBLICATION_MANIFEST.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    # Identifies the exact bundle even before semantic releases are introduced.
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12] + ' / ' + str(data.get('source_revision', 'unknown'))


def atomic_record(path, record):
    fd, temporary = tempfile.mkstemp(prefix='.receipt-', suffix='.json', dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(record, stream, indent=2)
            stream.flush();os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():temporary.unlink()


def describe(source, destination, checked_payload):
    source, root = safe_root(source), safe_root(destination)
    if source.is_relative_to(root) or root.is_relative_to(source):
        raise ValueError('Run the new installer from a separate extracted archive, outside the installation.')
    payload = checked_payload(source)
    if (root / '.installation-incomplete').exists():
        raise ValueError('Incomplete installation: use a new folder or restore your backup.')
    if not (root / 'uninstall-receipt.json').is_file():
        raise ValueError('No uninstall receipt: install in a new folder. Legacy ownership cannot be guessed.')
    _, record, _, _ = helper('uninstaller').plan(root)
    state = snapshot(root)
    owned = {entry['path'].casefold(): entry for entry in record['files']}
    private = {'.venv', '.test-cache'}
    personal = [name for name in state if name.casefold() not in owned
                and name != 'uninstall-receipt.json' and name.split('/')[0] not in private]
    new_names = {name.casefold() for name, _ in payload}
    new_names |= {'publication_manifest.json', 'installation.json', 'installation.log',
                  'start_hybridir.cmd', 'uninstall_hybridir.cmd', 'uninstall-receipt.json',
                  '.installation-incomplete'}
    for name in personal:
        folded = name.casefold()
        if state[name] is None:
            if folded in new_names:
                raise ValueError('Personal folder conflicts with new application file: ' + name)
        elif (folded in new_names or any(n.startswith(folded + '/') or folded.startswith(n + '/') for n in new_names)):
            raise ValueError('Personal file conflicts with new application files: ' + name)
    modified = [name for name, sha in state.items() if sha is not None
                and name.casefold() in owned and name.split('/')[0] not in private
                and sha != owned[name.casefold()]['sha256']]
    configuration = json.loads((root / 'installation.json').read_text(encoding='utf-8'))
    if configuration.get('schema') != 'hybridir-install/1':
        raise ValueError('Unsupported installed configuration')
    return dict(root=root, record=record, state=state, personal=personal,
                modified=modified, configuration=configuration,
                old_revision=revision(root), new_revision=revision(source))


def assert_not_running(root):
    """Also catches installations predating the launch mutex. Fail closed."""
    if os.name != 'nt':
        raise OSError('Updates require Windows')
    script = r'''
$ErrorActionPreference = 'Stop'
$prefix = $env:HYBRID_UPDATE_ROOT.TrimEnd('\') + '\'
$busy = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
    $_.ProcessId -ne [int]$env:HYBRID_UPDATE_PID -and (
        ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) -or
        ($_.CommandLine -and $_.Name -match '^(python|pythonw|py)(\.exe)?$' -and
         $_.CommandLine.IndexOf($prefix, [StringComparison]::OrdinalIgnoreCase) -ge 0)
    )
})
if ($busy.Count) { exit 23 }
'''
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand',
                    base64.b64encode(script.encode('utf-16le')).decode('ascii')],
                   env={**os.environ, 'HYBRID_UPDATE_ROOT': str(root), 'HYBRID_UPDATE_PID': str(os.getpid())},
                   check=True, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)


def vacant_sibling(root, label):
    path = Path(tempfile.mkdtemp(prefix=root.name + '.' + label + '-', dir=root.parent))
    path.rmdir()  # Our newly created empty reservation only; no user tree deletion.
    return path


def rename_tree(source, destination):
    source, destination = safe_root(source), safe_root(destination)
    if source.parent != destination.parent or destination.exists():
        raise ValueError('Unsafe update rename')
    source.rename(destination)


def update(source, destination, install, checked_payload, progress=lambda text: None, *, desktop_shortcut=False):
    root = safe_root(destination)
    with helper('installation_guard').installation_lock(root):
        assert_not_running(root)
        info = describe(source, root, checked_payload)
        config = info['configuration']
        full = bool(config.get('zdl_enabled'))
        ti = config.get('ti_root', '')
        donor = str(root / 'hybridir_sdk') if full else ''
        stage = vacant_sibling(root, 'staging')
        progress('Preparing verified candidate in ' + str(stage))
        # Keep existing app untouched if download, venv or smoke checks fail.
        try:
            install(source, stage, ti, donor, full, progress, desktop_shortcut=False)
        except Exception as exc:
            raise RuntimeError(f'Preparation failed; old installation unchanged. Candidate/logs: {stage}. {exc}') from exc
        if snapshot(root) != info['state']:
            raise RuntimeError('Installation changed during preparation; old version preserved. Retry after closing all applications.')
        assert_not_running(root)
        backup = vacant_sibling(root, 'backup')
        progress('Preserving complete old installation in ' + str(backup))
        journal = root.parent / (root.name + '.update.json')
        with journal.open('x', encoding='utf-8') as stream:
            json.dump(dict(root=str(root), backup=str(backup), stage=str(stage),
                           recovery='Close all HYBRID IR processes. Preserve any candidate at root elsewhere, then rename backup to root. Remove this journal only after recovery.'), stream, indent=2)
            stream.flush();os.fsync(stream.fileno())
        try:
            rename_tree(root, backup)
        except Exception:
            journal.unlink()
            raise
        try:
            # Recreate the venv here: moving a prepared venv breaks absolute launchers.
            install(source, root, ti, str(backup / 'hybridir_sdk') if full else '', full,
                    progress, desktop_shortcut=False, _allow_pending_update=True)
            for name in sorted(info['personal'], key=lambda n: (len(Path(n).parts), n)):
                old, new = backup / name, root / name
                if info['state'][name] is None:
                    new.mkdir(parents=True, exist_ok=True)
                else:
                    if new.exists():
                        raise ValueError('Refusing to overwrite personal file: ' + name)
                    new.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(old, new)
            # Preserve shortcut ownership without recreating/overwriting an existing .lnk.
            receipt_path = root / 'uninstall-receipt.json'
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
            receipt['shortcut'] = info['record'].get('shortcut')
            atomic_record(receipt_path, receipt)
        except Exception as exc:
            failed = vacant_sibling(root, 'failed')
            try:
                if root.exists():
                    rename_tree(root, failed)
                rename_tree(backup, root)
            except Exception as recovery:
                raise RuntimeError(f'Automatic rollback blocked. Old files remain in {backup}; candidate at {root} or {failed}. Close all processes before manual recovery. {recovery}') from exc
            journal.unlink()
            raise RuntimeError(f'Update failed; old installation restored. Failed candidate/logs: {failed}. {exc}') from exc
        journal.unlink()
        if desktop_shortcut and not receipt.get('shortcut'):
            try:
                shortcut = helper('installer').create_desktop_shortcut(root)
                receipt['shortcut'] = shortcut
                atomic_record(receipt_path, receipt)
            except Exception as exc:
                progress('Application installed, but desktop shortcut was not created. ' + str(exc))
        progress(f'Updated. Backup: {backup}. Prepared candidate: {stage}. Modified source files remain in the backup.')
        return dict(destination=root, backup=backup, stage=stage, modified=info['modified'])
