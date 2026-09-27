#!/usr/bin/env python3
"""Stdlib-only launcher. Installs missing dependencies once into a local venv."""
from pathlib import Path
import os
import subprocess
import sys
import venv

HERE=Path(__file__).resolve().parent

def check_runtime(version=None, maxsize=None):
    """Validate the interpreter without depending on installed DSP packages."""
    version = sys.version_info[:2] if version is None else tuple(version[:2])
    maxsize = sys.maxsize if maxsize is None else maxsize
    if not (3, 11) <= version <= (3, 14):
        raise RuntimeError('Use official 64-bit Python 3.11, 3.12, 3.13 or 3.14 with Tcl/Tk.')
    if maxsize <= 2**32:
        raise RuntimeError('IRBQ Lab needs a 64-bit Python interpreter, not 32-bit Python.')


def main():
    check_runtime()
    try:
        import tkinter
    except ImportError as e:
        raise RuntimeError('Tcl/Tk is missing. Windows: enable Tcl/Tk in Python installer. Linux: install python3-tk.') from e
    env=HERE/'.venv'
    exe=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not exe.exists():
        print('Creating local .venv ...',flush=True)
        venv.EnvBuilder(with_pip=True).create(env)
    check=subprocess.run([str(exe),'-c','import numpy, scipy, matplotlib, soundfile, tkinter'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if check.returncode:
        print('First run: installing dependencies. Internet access is needed for this step.',flush=True)
        subprocess.check_call([str(exe),'-m','pip','install','-r',str(HERE/'requirements.txt')])
    args=[str(exe),str(HERE/'run.py')]+sys.argv[1:]
    return subprocess.call(args,cwd=HERE)

if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('\nIRBQ Lab could not start:\n'+str(exc),file=sys.stderr)
        print('See README_RU.md. You can also install requirements manually.',file=sys.stderr)
        if sys.stdin.isatty():input('Press Enter to close...')
        raise SystemExit(1)
