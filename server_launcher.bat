@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

REM Comprobar que existe el venv
if not exist "venv\Scripts\python.exe" (
  echo [ERROR] No se encontro venv\Scripts\python.exe
  echo Crea el entorno virtual primero con: python -m venv venv
  pause
  exit /b 1
)

echo Iniciando servidor con el venv local...
"%~dp0venv\Scripts\python.exe" -m uvicorn api.app:app --reload --port 8000
pause
