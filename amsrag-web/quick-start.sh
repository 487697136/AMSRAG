#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

if [[ ! -d "$BACKEND_DIR" || ! -d "$FRONTEND_DIR" ]]; then
  echo "[ERROR] backend/frontend directories not found under $SCRIPT_DIR"
  exit 1
fi

if ! command -v python >/dev/null 2>&1; then
  echo "[ERROR] python is not available in PATH"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] npm is not available in PATH"
  exit 1
fi

export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"

echo "Starting backend..."
(
  cd "$BACKEND_DIR"
  python -m pip install -r requirements.txt >/dev/null 2>&1 || true
  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
) &
BACKEND_PID=$!

sleep 3

echo "Starting frontend..."
(
  cd "$FRONTEND_DIR"
  if [[ ! -d node_modules ]]; then
    npm install
  fi
  npm run dev
) &
FRONTEND_PID=$!

echo
echo "Launch complete"
echo "Frontend : http://127.0.0.1:5173"
echo "Backend  : http://127.0.0.1:8000"
echo "API Docs : http://127.0.0.1:8000/docs"
echo
echo "Press Ctrl+C to stop both services."

cleanup() {
  kill "$BACKEND_PID" "$FRONTEND_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

wait

