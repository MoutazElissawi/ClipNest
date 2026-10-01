@echo off
setlocal
cd /d "%~dp0"
rem Select a supported interpreter explicitly; never use the launcher default.
where py >nul 2>nul
if errorlevel 1 goto fallback
for %%V in (3.11 3.12 3.13) do (
    py -%%V -c "import struct,sys; sys.exit(0 if struct.calcsize('P') == 8 and (3,11) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "CLIPNEST_BUILD_VERSION=%%V"
        goto launcher_found
    )
)
:fallback
set "CLIPNEST_BUILD_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "CLIPNEST_BUILD_PYTHON=.venv\Scripts\python.exe"
"%CLIPNEST_BUILD_PYTHON%" -c "import struct,sys; sys.exit(0 if struct.calcsize('P') == 8 and (3,11) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>nul
if errorlevel 1 goto missing
"%CLIPNEST_BUILD_PYTHON%" -c "import sys; print('Building with:', sys.version); print(sys.executable)"
"%CLIPNEST_BUILD_PYTHON%" packaging\build_installer.py %*
goto done
:launcher_found
py -%CLIPNEST_BUILD_VERSION% -c "import sys; print('Building with:', sys.version); print(sys.executable)"
py -%CLIPNEST_BUILD_VERSION% packaging\build_installer.py %*
goto done
:missing
echo No supported 64-bit Python 3.11, 3.12 or 3.13 was found.
echo Installed launcher entries:
py -0p
echo Install a full python.org x64 build, or run the builder with its explicit python.exe path.
pause
exit /b 1
:done
if errorlevel 1 (
    echo.
    echo Build failed. Read the message above.
    pause
    exit /b 1
)
echo.
echo Build finished. See the dist folder.
pause
