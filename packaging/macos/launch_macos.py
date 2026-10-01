"""Native macOS entry point; no Windows installer, mutex or write inside the app."""
from __future__ import annotations
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import traceback

# Preserve the irbq_lab/irbq hierarchy so SDK-relative resource paths stay valid.
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def environment():
    from irbq_lab.irbq.app_paths import macos_cache_directory
    for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ.setdefault(key, '1')
    cache = Path(os.environ.get('HYBRIDIR_MAC_CACHE', macos_cache_directory()))
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR', str(cache / 'matplotlib'))
    log = cache / 'application.log'
    logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(log, maxBytes=1_000_000, backupCount=2, encoding='utf-8')])
    return log


def native_window():
    from irbq_lab.irbq.gui import App
    app = App()
    app.title('HYBRID IR — macOS preview')
    def open_documents(*paths):
        for path in paths:
            action = app.zoom_panel.open if str(path).lower().endswith('.hybridbank') else app.open_project
            app.after(0, lambda p=path, fn=action: fn(p))
    app.createcommand('::tk::mac::OpenDocument', open_documents)
    app.createcommand('::tk::mac::Quit', app.close)
    app.createcommand('::tk::mac::ReopenApplication', lambda: (app.deiconify(), app.lift()))
    app.bind('<Command-o>', lambda event: app.open_project())
    app.bind('<Command-s>', lambda event: app.save_active())
    app.bind('<Command-q>', lambda event: app.close())
    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', nargs='?')
    parser.add_argument('--self-test', type=Path, help='Create a NEW disposable test directory and report')
    parser.add_argument('--check-defaults', type=Path, help='Read-only fresh-process defaults regression')
    args = parser.parse_args(argv)
    if sys.platform != 'darwin':
        raise RuntimeError('This launcher is for macOS. Use irbq_lab/run.py on other systems.')
    if args.self_test:
        args.self_test.mkdir(parents=True, exist_ok=False)
        os.environ['IRBQ_SETTINGS_PATH'] = str(args.self_test / 'settings.json')
        os.environ['HYBRIDIR_MAC_CACHE'] = str(args.self_test / 'cache')
    elif args.check_defaults:
        from irbq_lab.irbq.preferences import load_preferences
        prefs = load_preferences(args.check_defaults)
        if prefs.prep_defaults.get('normalization') != 'k_pink_band' or prefs.prep_defaults.get('level_db') != -3.5:
            return 1
        return 0
    log = environment()
    if args.self_test:
        try:
            from irbq_lab.irbq.macos_selftest import run
            report = run(args.self_test, native_window)
        except Exception:
            report = dict(success=False, error=traceback.format_exc())
        (args.self_test / 'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        return 0 if report['success'] else 1
    try:
        app = native_window()
        if args.project:
            action = app.zoom_panel.open if args.project.lower().endswith('.hybridbank') else app.open_project
            app.after(250, lambda: action(args.project))
        app.mainloop()
        return 0
    except Exception:
        logging.exception('HYBRID IR could not start')
        from tkinter import Tk, messagebox
        window = Tk(); window.withdraw()
        messagebox.showerror('HYBRID IR', 'Could not start HYBRID IR. Details: '+str(log), parent=window)
        window.destroy()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
