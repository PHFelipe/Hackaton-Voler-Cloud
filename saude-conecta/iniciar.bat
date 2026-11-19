@echo off
REM Windows: clique duas vezes neste arquivo (ou: iniciar.bat testes)
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 run.py %*
) else (
  python run.py %*
)
if errorlevel 1 (
  echo.
  echo Se o Python nao foi encontrado, instale o Python 3.11+ em https://www.python.org/downloads/ marcando "Add python.exe to PATH".
)
pause
