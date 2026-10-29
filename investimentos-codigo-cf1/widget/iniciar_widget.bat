@echo off
rem Abre o widget da carteira sem janela de terminal.
rem Usa o Python do backend (.venv); se o backend estiver desligado, o widget liga.
setlocal
set "AQUI=%~dp0"
set "PYW=%AQUI%..\backend\.venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw"
start "" "%PYW%" "%AQUI%carteira_widget.py" --ligar-backend
