@echo off
setlocal
cd /d "%~dp0"
py -3.14 -c "import tkinter,sys; assert sys.maxsize > 2**32" >nul 2>&1
if errorlevel 1 (
  echo Install 64-bit Python 3.14 with Tcl/Tk, then run this file again.
  start "" "https://www.python.org/downloads/windows/"
  pause
  exit /b 1
)
py -3.14 -X utf8 "%~dp0installer.py"
if errorlevel 1 pause
