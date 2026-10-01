@echo off
setlocal
cd /d "%~dp0"
if exist "runtime\pythonw.exe" (
    start "" "runtime\pythonw.exe" -s -E "Launch_ClipNest.pyw"
    exit /b 0
)
if exist ".venv\Scripts\python.exe" goto ready
where py >nul 2>nul
if errorlevel 1 goto trypython
py -3 -m venv .venv
if errorlevel 1 goto failed
goto install
:trypython
where python >nul 2>nul
if errorlevel 1 goto missing
python -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "import PySide6, psutil, numpy" >nul 2>nul
if errorlevel 1 goto failed
goto launch
:ready
".venv\Scripts\python.exe" -c "import PySide6, psutil, numpy" >nul 2>nul
if errorlevel 1 goto install
:launch
".venv\Scripts\python.exe" bootstrap.py
if errorlevel 1 goto failed
start "" ".venv\Scripts\pythonw.exe" "Launch_ClipNest.pyw"
if errorlevel 1 goto failed
exit /b 0
:missing
echo Python 3.11 or newer is required. Install 64-bit Python from https://www.python.org/downloads/windows/
echo Enable the Python launcher during installation, then run this file again.
pause
exit /b 1
:failed
echo.
echo ClipNest could not start. Keep this window open and copy the error above.
pause
exit /b 1
