param(
    [string]$Python = "python",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8795,
    [switch]$SkipDataHashCheck
)

$ErrorActionPreference = "Stop"
$appRoot = $PSScriptRoot
Set-Location -LiteralPath $appRoot

& $Python --version
if ($LASTEXITCODE -ne 0) { throw "Python is unavailable: $Python" }

if (-not $SkipDataHashCheck) {
    & $Python (Join-Path $appRoot "scripts\verify_runtime_files.py")
    if ($LASTEXITCODE -ne 0) { throw "Runtime data verification failed" }
}

if (-not (Test-Path -LiteralPath (Join-Path $appRoot "backend\.env"))) {
    Write-Warning "backend\.env not found. Deterministic/GPKG mode can run, but PostGIS, LLM and CDSE require local configuration."
}

& $Python -m uvicorn main:app --app-dir (Join-Path $appRoot "backend") --host $HostAddress --port $Port
