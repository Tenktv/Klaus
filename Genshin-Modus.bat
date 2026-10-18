@echo off
powershell.exe -NoProfile -File "%~dp0Start-Genshin.ps1"
if errorlevel 1 pause
