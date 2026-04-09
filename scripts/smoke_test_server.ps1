$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$stdoutLog = Join-Path $root 'logs\smoke_stdout.log'
$stderrLog = Join-Path $root 'logs\smoke_stderr.log'
$uri = 'http://127.0.0.1:5000/'

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment not found at $venvPython"
}

if (Test-Path $stdoutLog) { Remove-Item $stdoutLog -Force }
if (Test-Path $stderrLog) { Remove-Item $stderrLog -Force }

$proc = Start-Process -FilePath $venvPython `
    -ArgumentList 'run_production.py' `
    -WorkingDirectory $root `
    -PassThru `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog

try {
    $response = $null
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 2
        try {
            $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                break
            }
        } catch {
            if ($proc.HasExited) {
                break
            }
        }
    }

    if ($null -eq $response) {
        Write-Host 'Smoke test failed.'
        if (Test-Path $stdoutLog) { Get-Content $stdoutLog -Tail 80 }
        if (Test-Path $stderrLog) { Get-Content $stderrLog -Tail 80 }
        exit 1
    }

    Write-Host "Smoke test passed with HTTP $($response.StatusCode)"
} finally {
    if (-not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force
    }
}
