param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'RupMES-Edge-Stable-Update')
)

$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'raspberry-stable-source\rupmes_edge'
if (-not (Test-Path (Join-Path $source 'app.py'))) {
    throw "No se encontró la copia estable de la Raspberry en: $source"
}

if (Test-Path $OutputDirectory) {
    Remove-Item -LiteralPath $OutputDirectory -Recurse -Force
}

$packageSource = Join-Path $OutputDirectory 'rupmes_edge'
New-Item -ItemType Directory -Path (Join-Path $packageSource 'static') -Force | Out-Null

foreach ($file in 'app.py', 'bmw_station_catalog.py', 'config.py', 'domain.py', 'opcua.py', 'runtime.py', 'process_metrics.py', 'store.py', 'stoppages.py', 'sync.py', '__init__.py') {
    Copy-Item -LiteralPath (Join-Path $source $file) -Destination (Join-Path $packageSource $file)
}
Copy-Item -LiteralPath (Join-Path $source 'static\index.html') -Destination (Join-Path $packageSource 'static\index.html')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'install-stable-update.sh') -Destination (Join-Path $OutputDirectory 'install-stable-update.sh')

Write-Host "Paquete creado: $OutputDirectory"
