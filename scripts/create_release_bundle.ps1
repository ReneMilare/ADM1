param(
    [string]$OutputDir = "dist",
    [string]$BundleName = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

if ([string]::IsNullOrWhiteSpace($BundleName)) {
    $BundleName = "ADM1-local-test-$timestamp"
}

$outputRoot = Join-Path $projectRoot $OutputDir
$stagingRoot = Join-Path $outputRoot ($BundleName + "-staging")
$zipPath = Join-Path $outputRoot ($BundleName + ".zip")

if (Test-Path $stagingRoot) {
    Remove-Item -Path $stagingRoot -Recurse -Force
}

if (Test-Path $zipPath) {
    Remove-Item -Path $zipPath -Force
}

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null

$topLevelItems = @(
    ".streamlit",
    "scripts",
    "simulator",
    "vendor",
    "webapp",
    ".gitignore",
    "pyproject.toml",
    "pytest.ini",
    "README.md",
    "requirements.txt"
)

function Get-RelativePath([string]$fullPath) {
    return $fullPath.Substring($projectRoot.Length).TrimStart('\\')
}

function Should-Exclude([string]$relativePath) {
    $path = $relativePath.Replace('/', '\\')
    $name = Split-Path $path -Leaf

    if ($name -in @('dynamic_out.csv', 'adm1-theme-probe.png')) { return $true }
    if ($name -like '*.pyc' -or $name -like '*.pyo' -or $name -like '*.pyd') { return $true }
    if ($path -match '(^|\\)(\.claude|\.venv|\.git)(\\|$)') { return $true }
    if ($path -match '(^|\\)pytest-cache-files-[^\\]+(\\|$)') { return $true }
    if ($path -match '(^|\\)root-probe-[^\\]+(\\|$)') { return $true }
    if ($path -match '(^|\\)__pycache__(\\|$)') { return $true }
    if ($path -match '(^|\\)\.pytest_cache(\\|$)') { return $true }
    if ($path -match '(^|\\)\.pytype(\\|$)') { return $true }
    if ($path -match '^webapp\\user_data(\\|$)') { return $true }
    if ($path -match '^simulator\\tests\\\.tmp(\\|$)') { return $true }
    if ($path -match '^simulator\\tests\\tmp_literature_validation(\\|$)') { return $true }
    if ($path -match '^simulator\\\.pyadm1_runtime\\probe-[^\\]+(\\|$)') { return $true }
    if ($path -match '^simulator\\\.pyadm1_runtime\\run-[^\\]+(\\|$)') { return $true }
    if ($path -match '^simulator\\\.pyadm1_runtime\\run_[^\\]+(\\|$)') { return $true }
    if ($path -match '^documentation(\\|$)') { return $true }
    if ($path -match '^vaultObsidian(AMD1)?(\\|$)') { return $true }
    if ($path -match '^dist(\\|$)') { return $true }

    return $false
}

foreach ($relativeItem in $topLevelItems) {
    $sourcePath = Join-Path $projectRoot $relativeItem
    if (-not (Test-Path $sourcePath)) {
        continue
    }

    $item = Get-Item -LiteralPath $sourcePath -Force
    if ($item -is [System.IO.DirectoryInfo]) {
        Get-ChildItem -LiteralPath $sourcePath -Recurse -Force -File -ErrorAction SilentlyContinue | ForEach-Object {
            $relativePath = Get-RelativePath $_.FullName
            if (Should-Exclude $relativePath) {
                return
            }

            $destinationPath = Join-Path $stagingRoot $relativePath
            $destinationDir = Split-Path -Parent $destinationPath
            if (-not (Test-Path $destinationDir)) {
                New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
            }
            Copy-Item -LiteralPath $_.FullName -Destination $destinationPath -Force
        }
    } else {
        $relativePath = Get-RelativePath $item.FullName
        if (-not (Should-Exclude $relativePath)) {
            $destinationPath = Join-Path $stagingRoot $relativePath
            $destinationDir = Split-Path -Parent $destinationPath
            if ($destinationDir -and -not (Test-Path $destinationDir)) {
                New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
            }
            Copy-Item -LiteralPath $item.FullName -Destination $destinationPath -Force
        }
    }
}

Compress-Archive -Path (Join-Path $stagingRoot "*") -DestinationPath $zipPath -CompressionLevel Optimal -Force

[PSCustomObject]@{
    BundleName = $BundleName
    ZipPath = $zipPath
    SizeMB = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
}
