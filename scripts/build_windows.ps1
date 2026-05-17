param(
    [string]$Python = "python",
    [string]$Version = "dev"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

Write-Host "Installing build dependencies..."
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt pyinstaller
Write-Host "Running unit tests before packaging..."
& $Python -m unittest discover -s tests -v

$releaseRoot = Join-Path $repoRoot "release"
$distRoot = Join-Path $repoRoot "dist"
$buildRoot = Join-Path $repoRoot "build"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $releaseRoot, $distRoot, $buildRoot
New-Item -ItemType Directory -Force $releaseRoot | Out-Null

$dataSeparator = ";"
$commonData = @(
    "--add-data", "category_config.json$dataSeparator.",
    "--add-data", "audio_model_catalog.json$dataSeparator.",
    "--add-data", "README.md$dataSeparator.",
    "--add-data", "LICENSE$dataSeparator.",
    "--add-data", ".env.example$dataSeparator."
)
$hiddenImports = @(
    "--hidden-import", "sklearn.linear_model._logistic",
    "--hidden-import", "sklearn.feature_extraction._dict_vectorizer",
    "--hidden-import", "sklearn.pipeline",
    "--hidden-import", "pygame"
)

Write-Host "Building GUI executable..."
& $Python -m PyInstaller --noconfirm --clean --onedir --name ClaveTagger-GUI --windowed @commonData @hiddenImports music_category_gui.py
Write-Host "Building CLI executable..."
& $Python -m PyInstaller --noconfirm --clean --onedir --name ClaveTagger-CLI --console @commonData @hiddenImports music_category_report.py

Write-Host "Preparing release folder..."
Copy-Item README.md, LICENSE, category_config.json, audio_model_catalog.json, .env.example -Destination $releaseRoot
Copy-Item -Recurse (Join-Path $distRoot "ClaveTagger-GUI") -Destination $releaseRoot
Copy-Item -Recurse (Join-Path $distRoot "ClaveTagger-CLI") -Destination $releaseRoot

$zipPath = Join-Path $repoRoot "ClaveTagger-windows-x64-$Version.zip"
Remove-Item -Force -ErrorAction SilentlyContinue $zipPath
Compress-Archive -Path (Join-Path $releaseRoot "*") -DestinationPath $zipPath
Write-Host "Created $zipPath"
