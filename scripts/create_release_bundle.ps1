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

# Security: the bundle must be built from a git checkout, never a filesystem walk.
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git nao foi encontrado no PATH. O bundle de release exige um checkout git."
}

& git -C $projectRoot rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) {
    throw "$projectRoot nao e um checkout git. O bundle de release exige git."
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

$submodulePath = "vendor/PyADM1"

function Should-Exclude([string]$relativePath) {
    $path = $relativePath.Replace('/', '\')
    $name = Split-Path $path -Leaf

    if ($name -in @('dynamic_out.csv', 'adm1-theme-probe.png', '.env')) { return $true }
    if ($name -like '*.pyc' -or $name -like '*.pyo' -or $name -like '*.pyd') { return $true }
    if ($name -like '.env.*') { return $true }
    if ($name -like '*.pem' -or $name -like '*.key') { return $true }
    if ($path -match '(^|\\)(\.claude|\.venv|\.git)(\\|$)') { return $true }
    if ($path -match '(^|\\)pytest-cache-files-[^\\]+(\\|$)') { return $true }
    if ($path -match '(^|\\)root-probe-[^\\]+(\\|$)') { return $true }
    if ($path -match '(^|\\)__pycache__(\\|$)') { return $true }
    if ($path -match '(^|\\)\.pytest_cache(\\|$)') { return $true }
    if ($path -match '(^|\\)\.pytype(\\|$)') { return $true }
    if ($path -match '^webapp\\user_data(\\|$)') { return $true }
    if ($path -match '^\.streamlit\\secrets\.toml$') { return $true }
    if ($path -match '^simulator\\tests\\\.tmp(\\|$)') { return $true }
    if ($path -match '^simulator\\tests\\tmp_literature_validation(\\|$)') { return $true }
    if ($path -match '^simulator\\runs(\\|$)') { return $true }
    if ($path -match '^simulator\\[^\\]*_runs(\\|$)') { return $true }
    if ($path -match '^simulator\\design_runs(\\|$)') { return $true }
    if ($path -match '^simulator\\\.pyadm1_runtime(\\|$)') { return $true }
    if ($path -match '^documentation(\\|$)') { return $true }
    if ($path -match '^vaultObsidian(AMD1)?(\\|$)') { return $true }
    if ($path -match '^dist(\\|$)') { return $true }

    return $false
}

function Copy-BundleFile([string]$relativePath) {
    $relativePath = $relativePath.Replace('/', '\')
    if (Should-Exclude $relativePath) {
        return
    }

    $sourcePath = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        return
    }

    $destinationPath = Join-Path $stagingRoot $relativePath
    $destinationDir = Split-Path -Parent $destinationPath
    if ($destinationDir -and -not (Test-Path $destinationDir)) {
        New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
    }
    Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Force
}

# Superproject tracked files, restricted to the same top-level items as before.
$trackedFiles = & git -C $projectRoot ls-files -- $topLevelItems
foreach ($relativePath in $trackedFiles) {
    if ($relativePath -eq $submodulePath) {
        continue
    }
    Copy-BundleFile $relativePath
}

# Submodule tracked files, prefixed with vendor/PyADM1/.
$submoduleAbs = (Join-Path $projectRoot $submodulePath).Replace('/', '\')
if (Test-Path (Join-Path $submoduleAbs '.git')) {
    $submoduleFiles = & git -C $submoduleAbs ls-files
    foreach ($file in $submoduleFiles) {
        Copy-BundleFile (Join-Path $submodulePath $file)
    }
} else {
    throw "O submódulo $submodulePath não está inicializado como checkout git."
}

# Post-build scan: refuse to ship secrets or keys even if a tracked file slipped through.
$forbidden = Get-ChildItem -LiteralPath $stagingRoot -Recurse -Force -File |
    Where-Object {
        $name = $_.Name
        $name -like '.env*' -or $name -eq 'secrets.toml' -or $name -like '*.pem' -or $name -like '*.key'
    }

if ($forbidden) {
    Remove-Item -Path $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $zipPath -Force -ErrorAction SilentlyContinue
    $names = ($forbidden | ForEach-Object { $_.FullName.Substring($stagingRoot.Length).TrimStart('\') }) -join ', '
    throw "O bundle contém arquivos proibidos (.env*, secrets.toml, *.pem, *.key): $names. Abortando sem gerar o bundle."
}

Compress-Archive -Path (Join-Path $stagingRoot "*") -DestinationPath $zipPath -CompressionLevel Optimal -Force

[PSCustomObject]@{
    BundleName = $BundleName
    ZipPath = $zipPath
    SizeMB = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
}
