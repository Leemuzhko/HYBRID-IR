"""Zoom Effect Manager folder package; separate from the patch audit report.

Contract: https://zoomeffectmanager.com/en/posts/reading-effects-from-folder/
"""
import io
import json
import os
from pathlib import Path
import shutil
import tempfile

from PIL import Image
from .app_paths import safe_output_directory


def manager_icon(image_png):
    """Export LCD artwork using the stock manager icon pixel/alpha convention."""
    with Image.open(io.BytesIO(image_png)) as source:
        if source.size != (128, 64):
            raise ValueError('Effect artwork must be 128x64')
        # Match the pedal's non-square pixels without introducing grey edges.
        mono = source.convert('L').point(lambda value: 255 if value >= 128 else 0)
        mono = mono.resize((128, 96), Image.Resampling.NEAREST)
        rgba = Image.merge('RGBA', (mono, mono, mono, mono.point(lambda value: 255 - value)))
        output = io.BytesIO()
        rgba.save(output, format='PNG')
        return output.getvalue()


def package_paths(project, output):
    folder = Path(output) / project.filename
    return {key: folder / (project.filename + suffix) for key, suffix in (
        ('zdl', '.zdl'), ('metadata', '.json'), ('image', '.png'),
        ('report', '.patch.json'))}


def check_package_paths(project, output, overwrite=False):
    output = safe_output_directory(output)
    paths = package_paths(project, output)
    folder = paths['zdl'].parent
    if folder.is_symlink() or folder.is_junction() or (folder.exists() and not folder.is_dir()):
        raise ValueError('Effect package folder must be a regular directory')
    # Do not leave two copies for the manager's recursive scanner.
    legacy = Path(output) / paths['zdl'].name
    if legacy.exists():
        raise ValueError('Move the previous flat ZDL export out of the Zoom Effect Manager folder before exporting: ' + str(legacy))
    for path in paths.values():
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError('Package output must be a regular file: ' + str(path))
        if path.exists() and not overwrite:
            raise FileExistsError(str(path))
    return paths


def manager_metadata(project):
    labels = ', '.join(slot.label for slot in project.slots)
    return dict(
        name=project.name,
        inDeviceFileName=project.filename + '.ZDL',
        iconFile=project.filename + '.png',
        descriptionEng=(f'HYBRID IR cabinet bank. IR slots: {labels}. '
                        'DSP cost is deliberately understated. If clicks or crackling occur, '
                        'reduce FIR length or disable one channel.'),
        descriptionRus=(f'Банк кабинетов HYBRID IR. Слоты IR: {labels}. '
                        'DSP-стоимость намеренно занижена. При щелчках или треске '
                        'уменьшите длину FIR или отключите один канал.'))


def publish_package(project, output, raw, image_png, report, overwrite=False):
    paths = check_package_paths(project, output, overwrite)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    payloads = dict(metadata=json.dumps(manager_metadata(project), ensure_ascii=False, indent=2).encode('utf-8'),
                    image=manager_icon(image_png), report=json.dumps(report, indent=2).encode('utf-8'), zdl=bytes(raw))
    folder = paths['zdl'].parent
    # Stage all bytes before touching existing exports. Publish the ZDL last.
    # Rollback handles ordinary write errors, not process termination/power loss.
    stage = Path(tempfile.mkdtemp(prefix='.hybridir-package-', dir=output))
    cleanup = True
    try:
        for key, data in payloads.items():
            (stage / key).write_bytes(data)
        check_package_paths(project, output, overwrite)
        created = not folder.exists()
        folder.mkdir(exist_ok=True)
        published, backups = [], {}
        try:
            for key in payloads:
                path = paths[key]
                if path.exists():
                    backup = stage / (key + '.old')
                    os.replace(path, backup)
                    backups[key] = backup
                os.replace(stage / key, path)
                published.append(key)
        except OSError:
            try:
                for key in reversed(published):
                    paths[key].unlink()
                for key, backup in backups.items():
                    os.replace(backup, paths[key])
                if created:
                    folder.rmdir()
            except OSError as recovery_error:
                cleanup = False
                raise OSError('Export rollback failed; recovery files retained in ' + str(stage)) from recovery_error
            raise
    finally:
        if cleanup:
            shutil.rmtree(stage)
    return paths['zdl']
