$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv (Join-Path $Root ".venv")
    } else {
        & python -m venv (Join-Path $Root ".venv")
    }
}
& $VenvPython -m pip install --upgrade pip
$ProjectSpec = "$Root[dev]"
& $VenvPython -m pip install -e $ProjectSpec

$Litex = Join-Path $Root "tools\litex\windows-amd64\litex.exe"
if (-not (Test-Path $Litex)) {
    throw "Bundled Litex executable not found: $Litex"
}
& $Litex -version
Write-Host "Setup complete. Run: powershell -ExecutionPolicy Bypass -File scripts\run_windows.ps1"
