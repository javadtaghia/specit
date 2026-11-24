$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $RootDir

$PythonBin = "python"
if (Test-Path "$RootDir\.venv\Scripts\python.exe") {
    $PythonBin = "$RootDir\.venv\Scripts\python.exe"
}

$Version = & $PythonBin -c "from engine.version import APP_VERSION; print(APP_VERSION)"
$OutExe = "SPECiT-$Version-Windows-x64.exe"

Write-Host "==> Building SPECiT $Version Windows standalone .exe"
& $PythonBin packaging/generate_icons.py
& $PythonBin -m PyInstaller --noconfirm --clean packaging/specit.spec

Copy-Item -Force "$RootDir\dist\SPECiT.exe" "$RootDir\dist\$OutExe"
Write-Host "==> Created dist\$OutExe"
