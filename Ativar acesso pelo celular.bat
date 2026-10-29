@echo off
rem Criado por launcher\dashboard.py (comando 'atalhos').
setlocal
chcp 65001 >nul
title Acesso pelo celular
set PYTHONIOENCODING=utf-8
set "PROJ=%~dp0investimentos-codigo-cf1"
if exist "%PROJ%\backend\.venv\Scripts\python.exe" (
  "%PROJ%\backend\.venv\Scripts\python.exe" "%PROJ%\launcher\dashboard.py" celular
) else (
  py -3 "%PROJ%\launcher\dashboard.py" celular
)
pause
