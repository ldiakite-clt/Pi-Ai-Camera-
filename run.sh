#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
source backend/venv/bin/activate
exec uvicorn backend.main:app --host 0.0.0.0 --port 8080
