@echo off
powershell.exe -NoProfile -File "%~dp0Start-Genshin.ps1" -Administrator
if errorlevel 1 pause
