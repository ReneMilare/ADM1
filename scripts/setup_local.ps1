[CmdletBinding()]
param(
    [string]$PythonExe = "python",
    [switch]$AutoApprove
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

$projectRoot = Get-Adm1ProjectRoot
$requirementsPath = Join-Path $projectRoot "requirements.txt"
$venvPython = Get-VenvPythonPath -ProjectRoot $projectRoot

Write-Section "Preparando ambiente Python"
$pythonLauncher = Resolve-PythonLauncher -Preferred $PythonExe
$pythonVersion = Get-PythonVersionString -Launcher $pythonLauncher
if (-not (Test-PythonVersionCompatible -VersionText $pythonVersion)) {
    throw "Python $pythonVersion encontrado, mas o projeto exige Python 3.11+."
}
Write-Note "Python detectado: $pythonVersion"

if (-not (Test-Path $venvPython)) {
    Write-Section "Criando ambiente virtual"
    Push-Location $projectRoot
    try {
        Invoke-PythonLauncher -Launcher $pythonLauncher -Arguments @("-m", "venv", ".venv")
    } finally {
        Pop-Location
    }
} else {
    Write-Note "Ambiente virtual ja existe em .venv"
}

Write-Section "Baixando submodulo vendor/PyADM1"
if ((Get-Command git -ErrorAction SilentlyContinue) -and (Test-Path (Join-Path $projectRoot ".git"))) {
    & git -C $projectRoot submodule update --init --recursive
} else {
    Write-Note "git indisponivel ou fora de um clone; confira se vendor/PyADM1 esta preenchido."
}

Write-Section "Instalando dependencias Python"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r $requirementsPath

Write-Section "Resumo do app principal"
Write-Note "A webapp principal nao inclui mais o RAG interno."
Write-Note "Os fluxos de simulacao, comparacao, design e validacao continuam disponiveis localmente."
Write-Note "Integracoes documentais futuras ficam fora do runtime principal do ADM1."

Write-Section "Concluido"
Write-Host "Proximo passo: .\scripts\run_webapp.ps1" -ForegroundColor Green
