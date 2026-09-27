@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto USE_PYTHON
for %%V in (3.14 3.13 3.12 3.11) do (
    py -%%V -c "import sys; assert sys.maxsize > 2**32" >nul 2>nul
    if not errorlevel 1 (
        set "IRBQ_PY_VERSION=%%V"
        goto USE_PY
    )
)
goto USE_PYTHON
:USE_PY
py -%IRBQ_PY_VERSION% bootstrap.py %*
goto DONE
:USE_PYTHON
python bootstrap.py %*
:DONE
set "IRBQ_RESULT=%ERRORLEVEL%"
if not "%IRBQ_RESULT%"=="0" pause
exit /b %IRBQ_RESULT%
