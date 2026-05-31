@echo off
cd /d "%~dp0"
set "PYTHONPATH=%~dp0.deps;%PYTHONPATH%"
python -c "import paramiko, keyring" >nul 2>nul
if errorlevel 1 (
  echo DeckShare dependencies are not installed.
  echo Run install_requirements.bat once, then start run.bat again.
  pause
  exit /b 1
)
python deckshare.py
