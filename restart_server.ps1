[CmdletBinding()]
param(
    [int]$Port = 5000
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$entryPoint = Join-Path $projectRoot 'run_production.py'
$logPath = Join-Path $projectRoot 'server.log'
$errorLogPath = Join-Path $projectRoot 'server-error.log'

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdministrator)) {
    Write-Host 'Requesting Administrator permission...'
    $arguments = @(
        '-NoProfile'
        '-ExecutionPolicy', 'Bypass'
        '-File', ('"{0}"' -f $PSCommandPath)
        '-Port', $Port
    )
    Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -Verb RunAs
    exit 0
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python environment not found: $pythonPath"
}
if (-not (Test-Path -LiteralPath $entryPoint)) {
    throw "Server entry point not found: $entryPoint"
}

Write-Host "Stopping NetMonitor on port $Port..."
$listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
$processIds = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)

foreach ($processId in $processIds) {
    if ($processId -and $processId -ne $PID) {
        Write-Host "Stopping process tree PID $processId"
        & taskkill.exe /PID $processId /T /F | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to stop process PID $processId"
        }
    }
}

$stopDeadline = (Get-Date).AddSeconds(15)
do {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $listener) { break }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $stopDeadline)

if ($listener) {
    throw "Port $Port is still occupied after 15 seconds"
}

Write-Host 'Starting NetMonitor production server...'
Start-Process -FilePath $pythonPath `
    -ArgumentList ('"{0}"' -f $entryPoint) `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput $logPath `
    -RedirectStandardError $errorLogPath `
    -WindowStyle Hidden

$startDeadline = (Get-Date).AddSeconds(30)
do {
    Start-Sleep -Milliseconds 500
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) { break }
} while ((Get-Date) -lt $startDeadline)

if (-not $listener) {
    Write-Host "Server did not start. Check: $logPath and $errorLogPath" -ForegroundColor Red
    exit 1
}

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/services/status" -TimeoutSec 10
    if ($health.task_scheduler_active -eq $false) {
        throw 'Web server started, but the task scheduler is not active.'
    }
} catch {
    Write-Host "Server is listening, but health verification failed: $($_.Exception.Message)" -ForegroundColor Yellow
    exit 1
}

Write-Host ''
Write-Host "NetMonitor restarted successfully: http://localhost:$Port" -ForegroundColor Green
Write-Host 'Trend data should begin returning after the first monitoring cycle.'
