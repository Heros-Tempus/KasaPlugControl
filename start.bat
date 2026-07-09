@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\pythonw.exe" (
    echo Virtual environment not found. Please follow the README instructions to set it up.
    pause
    exit /b
)
start "" "venv\Scripts\pythonw.exe" main.pyw