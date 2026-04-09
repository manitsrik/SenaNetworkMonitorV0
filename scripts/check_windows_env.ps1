$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment not found at $venvPython"
}

$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$nodeVersion = if ($nodeCommand) { (& $nodeCommand.Source --version) } else { 'missing' }

$executionPolicies = Get-ExecutionPolicy -List | ForEach-Object {
    [pscustomobject]@{
        Scope = $_.Scope
        ExecutionPolicy = $_.ExecutionPolicy
    }
}

$report = [pscustomobject]@{
    WindowsProductName = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').ProductName
    WindowsDisplayVersion = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').DisplayVersion
    WindowsBuild = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').CurrentBuild
    PowerShellVersion = $PSVersionTable.PSVersion.ToString()
    ActiveCodePage = ((chcp) -replace '[^\d]', '').Trim()
    ConsoleEncoding = [Console]::OutputEncoding.WebName
    SystemLocale = (Get-WinSystemLocale).Name
    TimeZone = (Get-TimeZone).Id
    GitVersion = (& git --version)
    PythonVersion = (& $venvPython --version)
    PipVersion = (& $venvPython -m pip --version)
    NodeVersion = $nodeVersion
}

$report | Format-List
Write-Host ''
'ExecutionPolicy:'
$executionPolicies | Format-Table -AutoSize
