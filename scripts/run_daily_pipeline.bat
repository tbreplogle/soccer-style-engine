@echo off
setlocal
set ROOT=%~dp0..
cd /d "%ROOT%"
if exist ".venv\Scripts\python.exe" (
  set PY=.venv\Scripts\python.exe
) else (
  set PY=python
)
%PY% -m src.cli run-daily-pipeline --as-of-date %DATE:~10,4%-%DATE:~4,2%-%DATE:~7,2% --skip-download --run-quick-audit --currentness-policy fail-on-unsafe
exit /b %ERRORLEVEL%
