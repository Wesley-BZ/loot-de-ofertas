$ErrorActionPreference = "Continue"
$projectDirectory = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectDirectory
New-Item -ItemType Directory -Path "logs" -Force | Out-Null
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$timestamp] Iniciando monitoramento" | Out-File -LiteralPath "logs\monitor.log" -Append -Encoding utf8
python -m loot_ofertas.cli publish wppconnect 2>&1 |
    Out-File -LiteralPath "logs\monitor.log" -Append -Encoding utf8
python -m loot_ofertas.cli discover-magalu --limit 30 --min-discount 10 2>&1 |
    Out-File -LiteralPath "logs\monitor.log" -Append -Encoding utf8
python -m loot_ofertas.cli discover-meli --limit 30 --min-discount 10 2>&1 |
    Out-File -LiteralPath "logs\monitor.log" -Append -Encoding utf8
$shopeeCredentials = "credenciais-shopee.env"
$shopeeConfigured = Test-Path -LiteralPath $shopeeCredentials -and
    (Select-String -Path $shopeeCredentials -Pattern '^SHOPEE_APP_ID=.+').Count -gt 0 -and
    (Select-String -Path $shopeeCredentials -Pattern '^SHOPEE_SECRET=.+').Count -gt 0
if ($shopeeConfigured) {
    python -m loot_ofertas.cli discover-shopee --limit 30 2>&1 |
        Out-File -LiteralPath "logs\monitor.log" -Append -Encoding utf8
}
python -m loot_ofertas.cli discover-deals --limit 60 2>&1 |
    Out-File -LiteralPath "logs\monitor.log" -Append -Encoding utf8
python -m loot_ofertas.cli monitor --limit 10 2>&1 |
    Out-File -LiteralPath "logs\monitor.log" -Append -Encoding utf8
exit 0
