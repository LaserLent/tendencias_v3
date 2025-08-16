@echo off
setlocal
rem Ir a la carpeta de este script (soporta rutas con espacios)
cd /d "%~dp0"

rem Crear venv si no existe (usa py o python según tengas)
if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creando entorno virtual...
  py -3 -m venv .venv 2>nul || python -m venv .venv
)

rem Lanzar Uvicorn con autoreload (no toca ExecutionPolicy)
".\.venv\Scripts\python.exe" -m uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload
