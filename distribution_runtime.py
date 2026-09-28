"""Delivery metadata and interpreter selection; never change DSP/template data."""
import json
import os
from pathlib import Path


def metadata(root):
    path = Path(root) / 'distribution.json'
    if not path.exists():
        return {'flavor': 'lite', 'channel': 'stable', 'version': 'legacy'}
    data = json.loads(path.read_text(encoding='utf-8'))
    if (data.get('schema') != 'hybridir-distribution/1'
            or data.get('flavor') not in ('lite', 'standalone')
            or data.get('channel') not in ('stable', 'development')):
        raise ValueError('Unsupported distribution metadata')
    return data


def interpreter(root, windowed=False):
    root = Path(root)
    if metadata(root)['flavor'] == 'standalone':
        return root / 'runtime' / ('pythonw.exe' if windowed else 'python.exe')
    return root / '.venv' / ('Scripts/pythonw.exe' if windowed else 'Scripts/python.exe')


def configure_preferences(root):
    if metadata(root)['channel'] == 'development':
        base = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
        os.environ.setdefault('IRBQ_SETTINGS_PATH', str(base / 'HYBRIDIR-Development/settings.json'))
