[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "RupMES-Edge-Production-Update")
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $projectRoot "src\rupmes_edge"

if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Output directory already exists: $OutputDirectory. Choose another path or remove that exact folder manually."
}

$targetSource = Join-Path $OutputDirectory "rupmes_edge"
$targetStatic = Join-Path $targetSource "static"
New-Item -ItemType Directory -Path $targetStatic -Force | Out-Null

foreach ($file in "app.py", "config.py", "domain.py", "opcua.py", "runtime.py", "store.py") {
    Copy-Item -LiteralPath (Join-Path $sourceRoot $file) -Destination $targetSource
}
Copy-Item -LiteralPath (Join-Path $sourceRoot "static\index.html") -Destination $targetStatic
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Install-Raspberry-ProductionUpdate.sh") -Destination $OutputDirectory

Write-Host "Update bundle created: $OutputDirectory"
Write-Host "Transfer it with: scp -r `"$OutputDirectory`" itsys@192.168.106.179`:~/"
