@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Set up the environment first. See GETTING_STARTED.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" flac_tagger.py
if errorlevel 1 pause
