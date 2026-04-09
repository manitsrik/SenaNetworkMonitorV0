$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$envCheck = Join-Path $PSScriptRoot 'check_windows_env.ps1'
$smokeCheck = Join-Path $PSScriptRoot 'smoke_test_server.ps1'
$pytestTarget = Join-Path $root 'tests\test_plugin_integrations.py'

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment not found at $venvPython"
}

Write-Host '== Environment =='
powershell -ExecutionPolicy Bypass -File $envCheck

Write-Host ''
Write-Host '== Pytest =='
& $venvPython -m pytest $pytestTarget

Write-Host ''
Write-Host '== Smoke Test =='
powershell -ExecutionPolicy Bypass -File $smokeCheck
