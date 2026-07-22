$ErrorActionPreference = "Stop"
$projectDirectory = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectDirectory
python -m uvicorn loot_ofertas.webapp:app --host 127.0.0.1 --port 8000
