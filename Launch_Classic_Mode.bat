@echo off
setlocal
cd /d "%~dp0"
if exist "runtime\pythonw.exe" (
    start "" "runtime\pythonw.exe" -s -E "Launch_ClipNest.pyw" --safe-ui
    exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "Launch_ClipNest.pyw" --safe-ui
    exit /b
)
echo Start ClipNest once with Start_ClipNest.bat to install dependencies first.
pause
