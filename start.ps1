# start.ps1
$ErrorActionPreference = "Stop"

# 1) Activar venv
if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
  Write-Error "No existe .\.venv\Scripts\Activate.ps1. Creá el venv e instalá dependencias."
}
. .\.venv\Scripts\Activate.ps1

# 2) (Opcional) asegurar PYTHONPATH a la raíz
$env:PYTHONPATH = (Get-Location).Path

# 3) Levantar API
python -m uvicorn service.main:app --reload --host 127.0.0.1 --port 8000
