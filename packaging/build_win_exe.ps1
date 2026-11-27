$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $RootDir

$PythonBin = "python"
if (Test-Path "$RootDir\.venv\Scripts\python.exe") {
    $PythonBin = "$RootDir\.venv\Scripts\python.exe"
}

$Version = & $PythonBin -c "from engine.version import APP_VERSION; print(APP_VERSION)"
$OutExe = "SPECiT-$Version-Windows-x64.exe"
$OutPath = "$RootDir\dist\$OutExe"

Write-Host "==> Building SPECiT $Version Windows standalone .exe"
& $PythonBin packaging/generate_icons.py
& $PythonBin -m PyInstaller --noconfirm --clean packaging/specit.spec

Copy-Item -Force "$RootDir\dist\SPECiT.exe" $OutPath

if ($env:WINDOWS_CERT_PFX -and (Test-Path $env:WINDOWS_CERT_PFX)) {
    Write-Host "==> Authenticode-signing $OutExe"
    $SignTool = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like "*\x64\signtool.exe" } |
        Sort-Object FullName -Descending |
        Select-Object -First 1 -ExpandProperty FullName

    if (-not $SignTool) {
        throw "signtool.exe not found in Windows Kits"
    }

    $SignArgs = @(
        "sign",
        "/fd", "SHA256",
        "/tr", "http://timestamp.digicert.com",
        "/td", "SHA256",
        "/d", "SPECiT Architecture & Specification Studio",
        "/du", "https://github.com/javadtaghia/specit",
        "/f", $env:WINDOWS_CERT_PFX
    )
    if ($env:WINDOWS_CERT_PASSWORD) {
        $SignArgs += @("/p", $env:WINDOWS_CERT_PASSWORD)
    }
    $SignArgs += $OutPath

    & $SignTool @SignArgs
    if ($LASTEXITCODE -ne 0) { throw "signtool sign failed with exit code $LASTEXITCODE" }

    & $SignTool verify /pa /v $OutPath
    if ($LASTEXITCODE -ne 0) { throw "signtool verify failed with exit code $LASTEXITCODE" }
    Write-Host "==> Verified Authenticode signature on $OutExe"
} else {
    Write-Host "==> Skipping Authenticode signing (set WINDOWS_CERT_PFX and WINDOWS_CERT_PASSWORD to enable)"
}

Write-Host "==> Created dist\$OutExe"
