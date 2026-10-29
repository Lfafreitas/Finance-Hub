@echo off
rem Cria um atalho "Carteira (widget)" na pasta Inicializar do Windows:
rem o widget abre sozinho quando voce entrar no computador.
rem Para desfazer, rode remover_inicio_automatico_windows.bat.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup') + '\Carteira (widget).lnk');" ^
  "$s.TargetPath = '%~dp0iniciar_widget.bat'; $s.WorkingDirectory = '%~dp0'; $s.WindowStyle = 7; $s.Save()"
echo Pronto: o widget vai abrir junto com o Windows.
pause
