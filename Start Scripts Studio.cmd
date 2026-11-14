@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" script_manager.py
    exit /b
)
where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw script_manager.py
    exit /b
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" script_manager.py
) else (
    python script_manager.py
)
if errorlevel 1 pause
