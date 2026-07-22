$ErrorActionPreference = "Stop"
$projectDirectory = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectDirectory
New-Item -ItemType Directory -Path "logs" -Force | Out-Null
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$timestamp] Iniciando monitoramento" | Out-File -LiteralPath "logs\monitor.log" -Append -Encoding utf8
python -m loot_ofertas.cli monitor --limit 50 --google 2>&1 |
    Out-File -LiteralPath "logs\monitor.log" -Append -Encoding utf8
