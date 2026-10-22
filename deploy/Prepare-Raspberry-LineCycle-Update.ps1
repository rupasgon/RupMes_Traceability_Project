param(
    [string]$OutputDirectory = "$env:USERPROFILE\Desktop\RupMES-Edge-LineCycle-Update"
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $projectRoot 'src\rupmes_edge'

if (Test-Path -LiteralPath $OutputDirectory) {
    throw "The output directory already exists: $OutputDirectory"
}

$packageSource = Join-Path $OutputDirectory 'rupmes_edge'
New-Item -ItemType Directory -Path $packageSource -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageSource 'static') -Force | Out-Null

foreach ($file in @('app.py', 'config.py', 'opcua.py', 'runtime.py')) {
    Copy-Item -LiteralPath (Join-Path $sourceRoot $file) -Destination $packageSource
}
Copy-Item -LiteralPath (Join-Path $sourceRoot 'static\index.html') -Destination (Join-Path $packageSource 'static\index.html')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Install-Raspberry-LineCycle-Update.sh') -Destination $OutputDirectory

Write-Host "Package ready: $OutputDirectory"
