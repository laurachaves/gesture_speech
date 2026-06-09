@echo off
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv not found
    echo Install uv first: https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

if not exist ".venv" (
    uv venv --python 3.10
)

echo Syncing dependencies
uv sync

echo Launching...
uv run python main.py

pause
