@echo off
rem Criado por launcher\dashboard.py (comando 'atalhos').
setlocal
chcp 65001 >nul
title Iniciar Dashboard
set PYTHONIOENCODING=utf-8
set "PROJ=%~dp0investimentos-codigo-cf1"
if exist "%PROJ%\backend\.venv\Scripts\python.exe" (
  "%PROJ%\backend\.venv\Scripts\python.exe" "%PROJ%\launcher\dashboard.py" iniciar
) else (
  py -3 "%PROJ%\launcher\dashboard.py" iniciar
)
if errorlevel 1 pause
