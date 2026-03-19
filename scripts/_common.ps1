Set-StrictMode -Version Latest

$Script:Adm1ProjectRoot = Split-Path -Parent $PSScriptRoot
$Script:Adm1DefaultEmbedModel = "nomic-embed-text"

function Get-Adm1ProjectRoot {
    return $Script:Adm1ProjectRoot
}

function Get-Adm1DefaultEmbedModel {
    return $Script:Adm1DefaultEmbedModel
}

function Write-Section {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Write-Note {
    param([string]$Message)
    Write-Host " - $Message" -ForegroundColor DarkGray
}

function Confirm-Action {
    param(
        [string]$Prompt,
        [bool]$Default = $true,
        [switch]$AutoApprove
    )

    if ($AutoApprove) {
        return $Default
    }

    $suffix = if ($Default) { "[Y/n]" } else { "[y/N]" }
    $response = Read-Host "$Prompt $suffix"
    if ([string]::IsNullOrWhiteSpace($response)) {
        return $Default
    }

    switch -Regex ($response.Trim().ToLowerInvariant()) {
        '^(y|yes|s|sim)$' { return $true }
        '^(n|no|nao|n?o)$' { return $false }
        default { return $Default }
    }
}

function Resolve-PythonLauncher {
    param([string]$Preferred = "python")

    $preferredCommand = Get-Command $Preferred -ErrorAction SilentlyContinue
    if ($preferredCommand) {
        return @($preferredCommand.Source)
    }

    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        return @($pyCommand.Source, "-3.11")
    }

    throw "Python 3.11+ nao foi encontrado no PATH. Instale Python antes de rodar este script."
}

function Invoke-PythonLauncher {
    param(
        [string[]]$Launcher,
        [string[]]$Arguments
    )

    $prefix = @()
    if ($Launcher.Count -gt 1) {
        $prefix = $Launcher[1..($Launcher.Count - 1)]
    }

    & $Launcher[0] @prefix @Arguments
}

function Get-PythonVersionString {
    param([string[]]$Launcher)

    $result = Invoke-PythonLauncher -Launcher $Launcher -Arguments @("-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))")
    return ($result | Select-Object -First 1).ToString().Trim()
}

function Test-PythonVersionCompatible {
    param([string]$VersionText)

    $parts = $VersionText.Split('.')
    if ($parts.Length -lt 2) {
        return $false
    }

    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    return ($major -gt 3) -or ($major -eq 3 -and $minor -ge 11)
}

function Get-VenvPythonPath {
    param([string]$ProjectRoot)
    return Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}

function Resolve-OllamaExe {
    $command = Get-Command ollama -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path ${env:ProgramFiles} "Ollama\ollama.exe")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    return $null
}

function Test-OllamaResponsive {
    param([string]$OllamaExe)

    if (-not $OllamaExe) {
        return $false
    }

    try {
        $null = & $OllamaExe list 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Start-OllamaServe {
    param([string]$OllamaExe)

    if (-not $OllamaExe) {
        return $false
    }

    try {
        Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden | Out-Null
        Start-Sleep -Seconds 4
        return $true
    } catch {
        return $false
    }
}

function Ensure-OllamaResponsive {
    param([string]$OllamaExe)

    if (Test-OllamaResponsive -OllamaExe $OllamaExe) {
        return $true
    }

    $null = Start-OllamaServe -OllamaExe $OllamaExe
    return (Test-OllamaResponsive -OllamaExe $OllamaExe)
}

function Get-OllamaModels {
    param([string]$OllamaExe)

    if (-not (Ensure-OllamaResponsive -OllamaExe $OllamaExe)) {
        return @()
    }

    $output = & $OllamaExe list 2>$null
    if ($LASTEXITCODE -ne 0) {
        return @()
    }

    return @(
        $output |
            Select-Object -Skip 1 |
            ForEach-Object {
                $name = (($_ -split '\s{2,}')[0]).Trim()
                if ($name) { $name }
            }
    )
}

function Test-RagIndexReady {
    param([string]$ProjectRoot)

    $dbDir = Join-Path $ProjectRoot "rag\db"
    if (-not (Test-Path $dbDir)) {
        return $false
    }

    return ((Get-ChildItem -Path $dbDir -Force -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0)
}

function Test-RagExtractedReady {
    param([string]$ProjectRoot)

    $extractedDir = Join-Path $ProjectRoot "rag\extracted"
    if (-not (Test-Path $extractedDir)) {
        return $false
    }

    return ((Get-ChildItem -Path $extractedDir -Filter *.json -File -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0)
}
