@echo off
title Klaus
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
if not exist ".venv\Scripts\python.exe" (
  echo Erste Einrichtung: installiere Klaus ...
  py -3.11 -m venv .venv || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
if not exist "data\stimmen\de_DE-thorsten-high.onnx" (
  echo Lade Klaus-Stimme ...
  ".venv\Scripts\python.exe" -m piper.download_voices --download-dir data\stimmen de_DE-thorsten-high
)
curl -s -m 2 http://localhost:11434/api/tags >nul 2>&1 || (
  echo Starte Ollama ...
  start "" /min ollama serve
  timeout /t 4 >nul
)
".venv\Scripts\python.exe" src\voice.py %*
echo.
pause
