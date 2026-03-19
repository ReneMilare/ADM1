[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

$projectRoot = Get-Adm1ProjectRoot
$venvPython = Get-VenvPythonPath -ProjectRoot $projectRoot
$embedModel = Get-Adm1DefaultEmbedModel

Write-Section "Estado local do ambiente"
Write-Note "Projeto: $projectRoot"

if (Test-Path $venvPython) {
    $pyVersion = & $venvPython -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    Write-Host "Python (.venv): $($pyVersion.Trim())" -ForegroundColor Green

    $importCheck = & $venvPython -c "import importlib.util; mods=['streamlit','numpy','pandas','plotly','pydantic','scipy','chromadb']; print('\n'.join(f'{name}=' + ('ok' if importlib.util.find_spec(name) else 'missing') for name in mods))"
    $importCheck | ForEach-Object { Write-Host $_ }
} else {
    Write-Warning "Ambiente virtual nao encontrado. Rode .\scripts\setup_local.ps1 primeiro."
}

$ollamaExe = Resolve-OllamaExe
if ($ollamaExe) {
    Write-Host "Ollama: instalado" -ForegroundColor Green
    if (Ensure-OllamaResponsive -OllamaExe $ollamaExe) {
        Write-Host "Ollama local: respondendo" -ForegroundColor Green
        $models = Get-OllamaModels -OllamaExe $ollamaExe
        if ($models | Where-Object { $_ -eq $embedModel -or $_ -like "${embedModel}:*" }) {
            Write-Host "Modelo de embedding ($embedModel): instalado" -ForegroundColor Green
        } else {
            Write-Warning "Modelo de embedding ($embedModel): ausente"
        }
    } else {
        Write-Warning "Ollama instalado, mas sem resposta local."
    }
} else {
    Write-Warning "Ollama nao encontrado."
}

if (Test-RagIndexReady -ProjectRoot $projectRoot) {
    Write-Host "Indice RAG: pronto" -ForegroundColor Green
} else {
    Write-Warning "Indice RAG: ausente ou vazio"
}

Write-Section "Leitura rapida"
Write-Host "- O app principal roda sem RAG." -ForegroundColor Gray
Write-Host "- Sem RAG, a parte de Consulta Tecnica fica limitada ou indisponivel." -ForegroundColor Gray
Write-Host "- Para abrir a interface: .\scripts\run_webapp.ps1" -ForegroundColor Gray
