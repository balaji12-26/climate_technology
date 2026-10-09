#!/usr/bin/env bash
# One-command demo launcher. Builds the UI if needed and serves everything on :8000.
cd "$(dirname "$0")"
[ -f frontend/dist/index.html ] || (cd frontend && npm install && npm run build)
.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
