$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RootDir
$env:PYINSTALLER_CONFIG_DIR = Join-Path $RootDir ".pyinstaller"

$PyInstaller = Join-Path $RootDir ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $PyInstaller)) {
    Write-Error 'PyInstaller not found. Run: .venv\Scripts\pip install -e ".[dev]"'
}

New-Item -ItemType Directory -Force `
    -Path $env:PYINSTALLER_CONFIG_DIR, (Join-Path $RootDir "build\pyinstaller"), (Join-Path $RootDir "dist") `
    | Out-Null

& $PyInstaller `
    --name Pnumi `
    --windowed `
    --clean `
    --noconfirm `
    --icon (Join-Path $RootDir "assets\pnumi.ico") `
    --add-data "$RootDir\assets\pnumi-icon.png;assets" `
    --paths (Join-Path $RootDir "src") `
    --distpath (Join-Path $RootDir "dist") `
    --workpath (Join-Path $RootDir "build\pyinstaller") `
    --specpath (Join-Path $RootDir "build\pyinstaller") `
    (Join-Path $RootDir "src\pnumi\__main__.py")

Write-Output "Built dist\Pnumi\Pnumi.exe"
