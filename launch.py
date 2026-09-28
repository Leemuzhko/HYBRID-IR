"""Installed application entry point; configuration stays on the user's machine."""
import json
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parent

def run_application():
    from distribution_runtime import configure_preferences
    configure_preferences(ROOT)
    configuration = ROOT / 'installation.json'
    if configuration.exists():
        settings = json.loads(configuration.read_text(encoding='utf-8'))
        os.environ['HYBRIDIR_ZDL_ENABLED'] = '1' if settings.get('zdl_enabled', True) else '0'
        if settings.get('ti_root'):
            os.environ['ZOOM_TI_ROOT'] = settings['ti_root']
    app = ROOT / 'irbq_lab'
    sys.path.insert(0, str(app))
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / '.test-cache' / 'matplotlib'))
    runpy.run_path(str(app / 'run.py'), run_name='__main__')


def main():
    from installation_guard import installation_lock
    try:
        with installation_lock(ROOT):
            run_application()
    except ValueError as exc:
        import tkinter as tk
        from tkinter import messagebox
        window=tk.Tk();window.withdraw()
        messagebox.showerror('HYBRID IR',str(exc),parent=window)
        window.destroy()

if __name__ == '__main__':
    main()
