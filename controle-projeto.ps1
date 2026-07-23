param(
    [ValidateSet("ligar", "desligar", "status", "menu")]
    [string]$Acao = "menu"
)

$ErrorActionPreference = "Continue"
$projectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$dashboardUrl = "http://127.0.0.1:8000/"
$taskName = "LootDeOfertas-Monitor"
$wppContainer = "wpp-server"

Set-Location -LiteralPath $projectDirectory

function Get-DashboardProcess {
    $listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
        if ($process.CommandLine -like "*uvicorn*loot_ofertas.webapp*") {
            return $process
        }
    }
    return $null
}

function Show-ProjectStatus {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    $taskInfo = if ($task) { Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue } else { $null }
    $dashboard = Get-DashboardProcess
    $dockerStatus = (& docker inspect --format "{{.State.Status}}" $wppContainer 2>$null)

    Write-Host ""
    Write-Host "Loot de Ofertas" -ForegroundColor Cyan
    Write-Host "Pasta:     $projectDirectory"
    Write-Host "Frontend:  $dashboardUrl"
    Write-Host "Monitor:   $(if ($task) { "$($task.State)" } else { "nao encontrado" })"
    Write-Host "Painel:    $(if ($dashboard) { "online (PID $($dashboard.ProcessId))" } else { "desligado" })"
    Write-Host "WhatsApp:  $(if ($dockerStatus) { $dockerStatus } else { "desligado/indisponivel" })"
    if ($taskInfo) {
        Write-Host "Ultimo ciclo:  $($taskInfo.LastRunTime)"
        Write-Host "Proximo ciclo: $($taskInfo.NextRunTime)"
    }
    Write-Host ""
}

function Start-Project {
    Write-Host "Ligando o Loot de Ofertas..." -ForegroundColor Green

    & docker start $wppContainer 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Nao consegui iniciar o WhatsApp. Confira se o Docker Desktop esta aberto."
    }

    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        Enable-ScheduledTask -TaskName $taskName | Out-Null
        Start-ScheduledTask -TaskName $taskName
    } else {
        Write-Warning "A tarefa $taskName nao foi encontrada."
    }

    if (-not (Get-DashboardProcess)) {
        Start-Process -FilePath "python" `
            -ArgumentList @("-m", "uvicorn", "loot_ofertas.webapp:app", "--host", "127.0.0.1", "--port", "8000") `
            -WorkingDirectory $projectDirectory `
            -WindowStyle Hidden
        $deadline = (Get-Date).AddSeconds(15)
        do {
            Start-Sleep -Milliseconds 500
            $dashboard = Get-DashboardProcess
        } until ($dashboard -or (Get-Date) -ge $deadline)
    }

    Start-Process $dashboardUrl
    Show-ProjectStatus
}

function Stop-Project {
    Write-Host "Desligando o Loot de Ofertas..." -ForegroundColor Yellow

    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Disable-ScheduledTask -TaskName $taskName | Out-Null
    }

    $dashboard = Get-DashboardProcess
    if ($dashboard) {
        Stop-Process -Id $dashboard.ProcessId -ErrorAction SilentlyContinue
    }

    & docker stop $wppContainer 2>$null | Out-Null
    Show-ProjectStatus
}

if ($Acao -eq "menu") {
    Clear-Host
    Write-Host "=== LOOT DE OFERTAS ===" -ForegroundColor Cyan
    Write-Host "1 - Ligar projeto e abrir o frontend"
    Write-Host "2 - Desligar projeto"
    Write-Host "3 - Mostrar status"
    $choice = Read-Host "Escolha"
    $Acao = switch ($choice) {
        "1" { "ligar" }
        "2" { "desligar" }
        "3" { "status" }
        default { "status" }
    }
}

switch ($Acao) {
    "ligar" { Start-Project }
    "desligar" { Stop-Project }
    "status" { Show-ProjectStatus }
}

if ($Host.Name -eq "ConsoleHost" -and $MyInvocation.InvocationName -notlike "*.ps1") {
    Read-Host "Pressione Enter para fechar"
}
