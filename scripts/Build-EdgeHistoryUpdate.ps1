[CmdletBinding()]
param(
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$OutputPath = if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    Join-Path $projectRoot "dist\RupMES-Edge-History-Update.zip"
} else {
    $OutputPath
}
$stageRoot = Join-Path $projectRoot "dist\RupMES-Edge-History-Update"
$payloadRoot = Join-Path $stageRoot "payload\src\rupmes_edge"

if (Test-Path -LiteralPath $stageRoot) {
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
}

New-Item -ItemType Directory -Path (Join-Path $payloadRoot "static") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Install-EdgeHistoryUpdate.ps1") -Destination $stageRoot -Force

foreach ($relativeFile in @("__main__.py", "app.py", "config.py", "runtime.py", "store.py", "static\index.html")) {
    $source = Join-Path $projectRoot "src\rupmes_edge\$relativeFile"
    $destination = Join-Path $payloadRoot $relativeFile
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
if (Test-Path -LiteralPath $OutputPath) {
    Remove-Item -LiteralPath $OutputPath -Force
}

Compress-Archive -Path (Join-Path $stageRoot "*") -DestinationPath $OutputPath -Force
Write-Host "Created: $OutputPath"
