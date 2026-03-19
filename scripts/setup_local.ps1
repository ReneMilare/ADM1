[CmdletBinding()]
param(
    [string]$PythonExe = "python",
    [switch]$SkipRag,
    [switch]$AutoApprove
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

$projectRoot = Get-Adm1ProjectRoot
$requirementsPath = Join-Path $projectRoot "requirements.txt"
$venvPython = Get-VenvPythonPath -ProjectRoot $projectRoot
$embedModel = Get-Adm1DefaultEmbedModel

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

Write-Section "Instalando dependencias Python"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r $requirementsPath

Write-Section "Resumo do app principal"
Write-Note "A webapp principal roda sem RAG."
Write-Note "Sem RAG, os fluxos de simulacao, comparacao, design e validacao continuam disponiveis."
Write-Note "A tela Consulta Tecnica passa a depender do indice local + Ollama + modelo de embedding."

if ($SkipRag) {
    Write-Section "Configuracao opcional do RAG ignorada por parametro"
} else {
    $enableRag = Confirm-Action -Prompt "Deseja habilitar agora a parte opcional do RAG/Consulta Tecnica?" -Default $true -AutoApprove:$AutoApprove
    if ($enableRag) {
        Write-Section "Verificando Ollama"
        $ollamaExe = Resolve-OllamaExe
        if (-not $ollamaExe) {
            $installOllama = Confirm-Action -Prompt "Ollama nao foi encontrado. Deseja instalar agora via winget?" -Default $true -AutoApprove:$AutoApprove
            if ($installOllama) {
                $winget = Get-Command winget -ErrorAction SilentlyContinue
                if (-not $winget) {
                    Write-Warning "winget nao esta disponivel. Instale Ollama manualmente em https://ollama.com/download/windows e rode novamente o setup se quiser o RAG."
                } else {
                    & $winget.Source install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
                }
                $ollamaExe = Resolve-OllamaExe
            }
        }

        if ($ollamaExe) {
            if (Ensure-OllamaResponsive -OllamaExe $ollamaExe) {
                Write-Note "Ollama detectado e respondendo."
                $models = Get-OllamaModels -OllamaExe $ollamaExe
                $modelInstalled = $models | Where-Object { $_ -eq $embedModel -or $_ -like "${embedModel}:*" } | Select-Object -First 1
                if (-not $modelInstalled) {
                    $pullModel = Confirm-Action -Prompt "O modelo de embedding '$embedModel' nao esta instalado. Deseja baixar agora?" -Default $true -AutoApprove:$AutoApprove
                    if ($pullModel) {
                        & $ollamaExe pull $embedModel
                    } else {
                        Write-Warning "Sem o modelo de embedding, a busca tecnica nao ficara funcional."
                    }
                } else {
                    Write-Note "Modelo '$embedModel' ja esta disponivel."
                }
            } else {
                Write-Warning "Ollama foi encontrado, mas nao respondeu localmente. A webapp ainda funciona; a busca tecnica ficara indisponivel ate o Ollama subir."
            }
        } else {
            Write-Warning "Ollama nao esta disponivel. A webapp principal continua funcional, mas a busca tecnica ficara indisponivel."
        }

        if (-not (Test-RagIndexReady -ProjectRoot $projectRoot)) {
            Write-Section "Verificando indice local do RAG"
            $buildRagIndex = Confirm-Action -Prompt "O indice vetorial local nao esta pronto. Deseja montar agora?" -Default $false -AutoApprove:$AutoApprove
            if ($buildRagIndex) {
                if (-not (Test-RagExtractedReady -ProjectRoot $projectRoot)) {
                    Write-Note "Extraindo PDFs para JSON estruturado..."
                    Push-Location $projectRoot
                    try {
                        & $venvPython (Join-Path $projectRoot "rag\extract_pdfs.py")
                    } finally {
                        Pop-Location
                    }
                }
                Write-Note "Indexando documentos no ChromaDB local..."
                Push-Location $projectRoot
                try {
                    & $venvPython (Join-Path $projectRoot "rag\index_documents.py")
                } finally {
                    Pop-Location
                }
            } else {
                Write-Warning "Sem indice local, a tela Consulta Tecnica abre mas a busca fica indisponivel ate a indexacao ser feita."
            }
        } else {
            Write-Note "Indice local do RAG ja esta pronto em rag/db."
        }
    } else {
        Write-Section "RAG mantido como opcional e desabilitado no setup"
        Write-Note "Nada do app principal depende disso para rodar localmente."
    }
}

Write-Section "Concluido"
Write-Host "Proximo passo: .\scripts\run_webapp.ps1" -ForegroundColor Green
