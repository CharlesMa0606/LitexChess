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
$HostAddress = if ($env:HOST) { $env:HOST } else { "127.0.0.1" }
$PortNumber = if ($env:PORT) { $env:PORT } else { "8000" }
& $Python -m uvicorn litex_chess.api:app --host $HostAddress --port $PortNumber --reload
