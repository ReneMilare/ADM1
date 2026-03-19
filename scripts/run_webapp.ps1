[CmdletBinding()]
param(
    [int]$Port = 8501,
    [switch]$Headless
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

$projectRoot = Get-Adm1ProjectRoot
$venvPython = Get-VenvPythonPath -ProjectRoot $projectRoot
if (-not (Test-Path $venvPython)) {
    throw "Ambiente virtual nao encontrado. Rode .\scripts\setup_local.ps1 primeiro."
}

Write-Section "Subindo webapp local"
Write-Note "Projeto: $projectRoot"
Write-Note "Porta: $Port"

$streamlitArgs = @(
    "-m",
    "streamlit",
    "run",
    (Join-Path $projectRoot "webapp\app.py"),
    "--server.port",
    "$Port"
)
if ($Headless) {
    $streamlitArgs += @("--server.headless", "true")
}

Push-Location $projectRoot
try {
    & $venvPython @streamlitArgs
} finally {
    Pop-Location
}
