@echo off
rem doc-translator - one-click GUI launcher (Windows).
rem
rem First run:
rem   - installs uv (under %USERPROFILE%\.local\bin) if missing
rem   - syncs dependencies via `uv sync`
rem   - downloads babeldoc layout models on first translation (needs network)
rem Subsequent runs:
rem   - `uv sync` is a near-instant no-op when nothing changed
rem
rem Defaults:
rem   Port 7860, bound to 0.0.0.0 so other machines on the LAN can reach it
rem   (open http://<this-host-ip>:7860 from a phone/laptop in the same network).
rem
rem Override defaults via env vars before running, e.g.:
rem   set DT_PORT=18080
rem   set DT_AUTH=D:\path\to\auth.txt  (format: user:password, one per line)
rem   run-gui.bat

setlocal
cd /d "%~dp0\.."

if "%DT_PORT%"=="" set DT_PORT=7860

where uv >nul 2>&1
if errorlevel 1 (
    echo [1/3] Installing uv ...
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if errorlevel 1 goto :err_install
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

echo [2/3] Syncing dependencies ...
uv sync
if errorlevel 1 goto :err_sync

echo [3/3] Launching GUI on http://0.0.0.0:%DT_PORT% ...
if "%DT_AUTH%"=="" (
    uv run translator --gui --server-port %DT_PORT%
) else (
    uv run translator --gui --server-port %DT_PORT% --auth-file "%DT_AUTH%"
)
goto :eof

:err_install
echo.
echo Failed to install uv. Check your network / proxy and try again.
pause
exit /b 1

:err_sync
echo.
echo `uv sync` failed. Common causes: no network, wrong Python version, or corrupt pyproject.toml.
pause
exit /b 1
