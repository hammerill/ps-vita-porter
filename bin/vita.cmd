@echo off
rem ps-vita-porter CLI launcher for cmd.exe / PowerShell (bin/vita is the bash one).
if defined VITA_PORTER_NO_UV goto nouv
where uv >NUL 2>NUL || goto nouv
uv run --quiet --project "%~dp0.." python -m vita_porter %*
exit /b %ERRORLEVEL%
:nouv
set "PYTHONPATH=%~dp0..;%PYTHONPATH%"
python -m vita_porter %*
exit /b %ERRORLEVEL%
