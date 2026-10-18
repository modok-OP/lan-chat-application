#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$DIR"

echo "==================================================="
echo "Starting LAN Chat Application Server (Backend)"
echo "==================================================="

if [ ! -f "backend/.venv/bin/python" ]; then
    echo "[ERROR] Virtual environment not found at backend/.venv"
    echo "Run:"
    echo "  python3 -m venv backend/.venv"
    echo "  backend/.venv/bin/pip install -r backend/requirements.txt"
    exit 1
fi

source backend/.venv/bin/activate
cd backend
echo "[INFO] Launching Uvicorn server on http://0.0.0.0:8000 ..."
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
