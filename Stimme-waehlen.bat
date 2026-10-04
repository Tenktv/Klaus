@echo off
title Klaus - Stimme waehlen
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" src\stimmen_test.py
echo.
pause
