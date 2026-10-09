# One-command demo launcher (Windows PowerShell). Builds the UI if needed and serves everything on :8000.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path "$root\frontend\dist\index.html")) { Push-Location "$root\frontend"; npm install; npm run build; Pop-Location }
& "$root\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir "$root\backend" --host 127.0.0.1 --port 8000
