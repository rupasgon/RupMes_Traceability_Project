[CmdletBinding()]
param(
    [string]$InstallRoot = "C:\Program Files\RupMES Edge",
    [string]$TaskName = "RupMES Edge Dashboard"
)

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this update as Administrator."
}

$payloadRoot = Join-Path $PSScriptRoot "payload\src\rupmes_edge"
$targetRoot = Join-Path $InstallRoot "src\rupmes_edge"
$files = @("__main__.py", "app.py", "config.py", "runtime.py", "store.py", "static\index.html")

if (-not (Test-Path -LiteralPath $targetRoot)) {
    throw "RupMES Edge was not found in: $InstallRoot"
}

foreach ($relativeFile in $files) {
    $source = Join-Path $payloadRoot $relativeFile
    $destination = Join-Path $targetRoot $relativeFile
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Update payload is incomplete: $source"
    }

    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

$configPath = Join-Path $env:ProgramData "RupMES Edge\config.json"
if (Test-Path -LiteralPath $configPath) {
    $tokenReference = (Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json).admin.token_secret_ref
    if ($tokenReference -and -not [Environment]::GetEnvironmentVariable($tokenReference, "Machine")) {
        $tokenBytes = New-Object byte[] 32
        $random = [Security.Cryptography.RandomNumberGenerator]::Create()
        $random.GetBytes($tokenBytes)
        $random.Dispose()
        $adminToken = [Convert]::ToBase64String($tokenBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
        [Environment]::SetEnvironmentVariable($tokenReference, $adminToken, "Machine")
        Write-Host "Initial Edge administrator token (save it now): $adminToken" -ForegroundColor Yellow
    }
}

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName $TaskName

Write-Host "RupMES Edge history update installed. Reload http://127.0.0.1:8020/edge"
