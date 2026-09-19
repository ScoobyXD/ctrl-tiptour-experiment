@echo off
title [CTRL] Hybrid experiment - TipTour Windows browser adaptation
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-CTRL.ps1"
if errorlevel 1 pause
