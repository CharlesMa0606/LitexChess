$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Litex = Join-Path $Root "tools\litex\windows-amd64\litex.exe"
if (-not (Test-Path $Litex)) {
    throw "Bundled Litex executable not found: $Litex"
}
$env:LITEX_BIN = $Litex
$env:LITEXPY_LITEX_BIN = $Litex
$env:PYTHONPATH = (Join-Path $Root "backend")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}
& $Python (Join-Path $Root "scripts\verify_release.py")
exit $LASTEXITCODE
