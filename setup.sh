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

# Try to install picamera2 into the venv (may be needed on Pi)
echo "Checking picamera2 in venv..."
python - <<'PY'
import importlib, sys
try:
    import picamera2
    print('picamera2 python package present in venv')
except Exception as e:
    print('picamera2 not importable in venv:', e)
    print('Attempting pip install picamera2...')
    sys.exit(2)
PY
if [ $? -eq 2 ]; then
  pip install picamera2 || true
fi

echo "Created/updated backend virtualenv and installed requirements."
echo
echo "If you plan to use the Pi camera hardware (Picamera2 + libcamera), you may also need system packages."
echo "On Raspberry Pi OS run (with sudo):"
echo "  sudo apt update && sudo apt install -y python3-libcamera python3-picamera2 libcamera-apps"
echo
echo "To run the server:"
echo "  source backend/venv/bin/activate"
echo "  ./run.sh"
