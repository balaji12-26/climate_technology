# One-command demo launcher (Windows PowerShell).
# Builds the frontend if frontend/dist is missing, then serves API + UI on http://127.0.0.1:8000.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "No virtualenv found at .venv. Run the 'Fresh setup' commands in DEMO.md first." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $root "frontend\dist\index.html"))) {
    Write-Host "frontend/dist missing - installing npm packages and building the UI..." -ForegroundColor Yellow
    Push-Location (Join-Path $root "frontend")
    try {
        npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed (exit $LASTEXITCODE)" }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed (exit $LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
    Write-Host "Frontend built." -ForegroundColor Green
} else {
    Write-Host "frontend/dist present - skipping build (delete it to force a rebuild)."
}

Write-Host "Starting server on http://127.0.0.1:8000 (Ctrl+C to stop)" -ForegroundColor Green
& $python -m uvicorn app.main:app --app-dir (Join-Path $root "backend") --host 127.0.0.1 --port 8000
