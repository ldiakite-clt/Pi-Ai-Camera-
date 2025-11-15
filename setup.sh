#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [ ! -d backend/venv ]; then
  python3 -m venv backend/venv
fi
source backend/venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt

echo "Created/updated backend virtualenv and installed requirements."
echo "To run the server:"
echo "  source backend/venv/bin/activate"
echo "  uvicorn backend.main:app --host 0.0.0.0 --port 8080"
