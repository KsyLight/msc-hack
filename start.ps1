param([ValidateSet('demo','real')][string]$Mode, [int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $Mode) {
    $Mode = if ($env:APP_MODE) { $env:APP_MODE } elseif (Test-Path -LiteralPath 'runtime/real/dataset.json') { 'real' } else { 'demo' }
}
$env:APP_MODE = $Mode
$env:OMP_NUM_THREADS = '4'
$env:OPENBLAS_NUM_THREADS = '4'
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) {
    Push-Location -LiteralPath 'frontend'
    try {
        npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    } finally { Pop-Location }
}
Write-Host "Dashboard: http://localhost:$Port | API: http://localhost:$Port/docs | mode: $Mode"
conda run --no-capture-output -n msc-hack python -m uvicorn backend.main:app --host 127.0.0.1 --port $Port
if ($LASTEXITCODE -ne 0) { throw 'API failed to start; see output above' }
