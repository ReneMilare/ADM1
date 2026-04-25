[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

$projectRoot = Get-Adm1ProjectRoot
$venvPython = Get-VenvPythonPath -ProjectRoot $projectRoot

Write-Section "Estado local do ambiente"
Write-Note "Projeto: $projectRoot"

if (Test-Path $venvPython) {
    $pyVersion = & $venvPython -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    Write-Host "Python (.venv): $($pyVersion.Trim())" -ForegroundColor Green

    $importCheck = & $venvPython -c "import importlib.util; mods=['streamlit','numpy','pandas','plotly','pydantic','scipy']; print('\n'.join(f'{name}=' + ('ok' if importlib.util.find_spec(name) else 'missing') for name in mods))"
    $importCheck | ForEach-Object { Write-Host $_ }
} else {
    Write-Warning "Ambiente virtual nao encontrado. Rode .\scripts\setup_local.ps1 primeiro."
}

Write-Section "Leitura rapida"
Write-Host "- O app principal roda sem RAG interno." -ForegroundColor Gray
Write-Host "- Os fluxos de simulacao, comparacao, design e validacao continuam locais." -ForegroundColor Gray
Write-Host "- Para abrir a interface: .\scripts\run_webapp.ps1" -ForegroundColor Gray
