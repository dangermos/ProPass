#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$PROJECT_ROOT"
if [[ ! -x .venv/bin/python || ! -d web/node_modules ]]; then
  echo "Install the Python and web dependencies described in README.md first."
  exit 1
fi
if .venv/bin/python - <<'PY'
import urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=1) as r:
        assert r.status == 200
    with urllib.request.urlopen('http://127.0.0.1:5173/', timeout=1) as r:
        assert r.status == 200
except Exception:
    raise SystemExit(1)
PY
then
  echo "ProPass is already running: http://127.0.0.1:5173/"
  exit 0
fi
mkdir -p artifacts/logs
.venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port 8000 --no-access-log > artifacts/logs/api.log 2>&1 &
API_PID=$!
(cd web && exec npm run dev -- --port 5173 --strictPort) > artifacts/logs/web.log 2>&1 &
WEB_PID=$!
cleanup() {
  kill "$API_PID" "$WEB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
echo "Dashboard: http://127.0.0.1:5173/"
echo "Open Assets/ProPass/Scenes/Checkout.unity in Unity and press Play."
echo "Keep this terminal open. Ctrl+C stops these two services. Logs: artifacts/logs/"
wait -n "$API_PID" "$WEB_PID"
