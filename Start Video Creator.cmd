@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" create_video.py
) else (
    python create_video.py
)
if errorlevel 1 pause
