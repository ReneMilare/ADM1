Set-StrictMode -Version Latest

$Script:Adm1ProjectRoot = Split-Path -Parent $PSScriptRoot

function Get-Adm1ProjectRoot {
    return $Script:Adm1ProjectRoot
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
