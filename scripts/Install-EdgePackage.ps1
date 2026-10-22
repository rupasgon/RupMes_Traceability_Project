[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:ProgramFiles "RupMES Edge"),
    [string]$DataRoot = (Join-Path $env:ProgramData "RupMES Edge"),
    [string]$TaskName = "RupMES Edge Dashboard",
    [string]$PythonExe = "python",
    [string]$AdminToken
)

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this installer with 'Run as administrator'."
}

$packageRoot = Split-Path -Parent $PSCommandPath
$sourceRoot = Join-Path $packageRoot "app"
$wheelDirectory = Join-Path $packageRoot "wheels"
$requirements = Join-Path $packageRoot "edge-requirements.txt"
$template = Join-Path $packageRoot "config.example.json"
$configPath = Join-Path $DataRoot "config.json"

if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot "src\rupmes_edge"))) {
    throw "Invalid package: app\src\rupmes_edge is missing."
}

New-Item -ItemType Directory -Force -Path $InstallRoot, $DataRoot, (Join-Path $DataRoot "certificates"), (Join-Path $DataRoot "data") | Out-Null
Copy-Item -Path (Join-Path $sourceRoot "*") -Destination $InstallRoot -Recurse -Force

$venvPath = Join-Path $InstallRoot ".venv"
if (-not (Test-Path -LiteralPath $venvPath)) {
    & $PythonExe -m venv $venvPath
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"
$vendorRuntime = Join-Path $InstallRoot "vendor\runtime.json"
if (Test-Path -LiteralPath $vendorRuntime -PathType Leaf) {
    $runtime = Get-Content -Raw -LiteralPath $vendorRuntime | ConvertFrom-Json
    $targetVersion = (& $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ($targetVersion -ne $runtime.python_major_minor) {
        throw "This package requires Python $($runtime.python_major_minor), but the selected Python is $targetVersion."
    }
    Write-Host "Using bundled Edge dependencies for Python $targetVersion." -ForegroundColor Green
} elseif (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
    throw "Dependency manifest is missing: $requirements"
} elseif (Test-Path -LiteralPath $wheelDirectory -PathType Container) {
    & $venvPython -m pip install --no-index --find-links $wheelDirectory -r $requirements
} else {
    Write-Host "Offline bundle not found. Downloading Edge dependencies from the configured Python repository..." -ForegroundColor Yellow
    & $venvPython -m pip install -r $requirements
}
if (-not (Test-Path -LiteralPath $vendorRuntime) -and $LASTEXITCODE -ne 0) {
    throw "The Edge dependencies could not be installed. The Windows service was not registered."
}

if (-not (Test-Path -LiteralPath $configPath)) {
    Copy-Item -LiteralPath $template -Destination $configPath
    Write-Host "Configuration template created: $configPath" -ForegroundColor Yellow
} else {
    Write-Host "Existing configuration preserved: $configPath" -ForegroundColor Green
}

$tokenReference = (Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json).admin.token_secret_ref
if ($tokenReference) {
    $existingToken = [Environment]::GetEnvironmentVariable($tokenReference, "Machine")
    if (-not $existingToken) {
        if (-not $AdminToken) {
            $tokenBytes = New-Object byte[] 32
            $random = [Security.Cryptography.RandomNumberGenerator]::Create()
            $random.GetBytes($tokenBytes)
            $random.Dispose()
            $AdminToken = [Convert]::ToBase64String($tokenBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
        }
        [Environment]::SetEnvironmentVariable($tokenReference, $AdminToken, "Machine")
        Write-Host "`nInitial Edge administrator token (save it now): $AdminToken" -ForegroundColor Yellow
        Write-Host "It is stored as the machine variable $tokenReference and is needed in the Configuration window."
    }
}

$serviceInstaller = Join-Path $InstallRoot "scripts\Install-EdgeWindowsService.ps1"
& $serviceInstaller -ProjectRoot $InstallRoot -PythonExe $venvPython -ConfigPath $configPath -TaskName $TaskName

Write-Host "`nInstallation complete." -ForegroundColor Green
Write-Host "1. Edit: $configPath"
Write-Host "2. Add OPC UA certificates under: $(Join-Path $DataRoot 'certificates')"
Write-Host "3. Set RUPMES_EDGE_OPCUA_PASSWORD and RUPMES_EDGE_ADMIN_TOKEN as machine environment variables."
Write-Host "4. Start it: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "5. The station daily-history charts are included in this installer."
