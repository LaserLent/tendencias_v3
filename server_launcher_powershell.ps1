# run_server.ps1
Set-Location -Path $PSScriptRoot

$python = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  Write-Host "[ERROR] No se encontró $python" -ForegroundColor Red
  Write-Host "Crea el entorno: python -m venv venv"
  Read-Host "Pulsa Enter para salir"
  exit 1
}

[Console]::OutputEncoding = [Text.UTF8Encoding]::UTF8
& $python -m uvicorn api.app:app --reload --port 8000
Read-Host "Servidor detenido. Pulsa Enter para cerrar"
