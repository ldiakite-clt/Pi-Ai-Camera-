Pi-Ai-Camera - Code Summary (Dumbed-down, modular)

This file is a compact, plain-language map of the project so you can quickly remember where things live and what they do.

High-level
----------
- What this does: run a small local web app on a Raspberry Pi which serves a live MJPEG stream of the Pi camera, allows taking photos, storing them, and downloading short replay zip files. A WebSocket pushes low-fps frames/events to the frontend.
- Main pieces:
  - Backend (FastAPI + Uvicorn) that talks to the camera and serves API/static files.
  - Frontend (static HTML/JS under `PiDoorCam/`) that shows Live, Photos, Heatmap pages.
  - Local storage under `backend/data/` (photos, thumbnails, sqlite DB).

Files you will use most
-----------------------
- run.sh
  - Starts the backend (activates venv and runs uvicorn). Useful for development on the Pi.
  - PID file: `/tmp/pidoorcam_uvicorn.pid`
  - Log file: `/tmp/pidoorcam_uvicorn.log`

- setup.sh
  - Installs system packages and creates the Python venv (if present). Use this first when provisioning a fresh Pi.

- Backend (directory: `backend/`)
  - `backend/main.py`
    - FastAPI app and main HTTP/WebSocket endpoints.
    - Key routes:
      - `GET /stream.mjpg` -> MJPEG stream (multipart/x-mixed-replace)
      - `GET /camera/frame` -> single JPEG frame
      - `POST /api/photo` -> take & save a photo (creates thumbnail)
      - `GET /api/photos` -> list saved photos
      - `GET /api/replay?seconds=N` -> download zip of recent frames
      - `GET /data/photos/{filename}` -> serve saved photo
      - `GET /ws` (WebSocket) -> receives JSON frames/events
    - Static frontend is mounted at `/` and serves files from `PiDoorCam/`.

  - `backend/camera.py`
    - Camera wrapper around Picamera2.
    - Exposes a singleton `get_global_camera()` that the app uses.
    - Responsibilities:
      - Initialize Picamera2 (if available) and keep a short in-memory replay buffer (deque) of recent JPEG frames.
      - `get_frame()` returns the latest JPEG bytes (or a fallback placeholder when the camera is unavailable).
    - Important fix: captured arrays can be RGBA (4 channels). Pillow cannot save RGBA directly as JPEG -> we convert `RGBA` -> `RGB` before encoding. This prevented an earlier crash where the app returned the placeholder.
    - Notes: If another process or service has the camera (/dev/media0) open (rpicam preview, PipeWire/wireplumber, another app), libcamera reports "device busy" and the camera initialization fails. Stop those processes to allow the backend to open the camera.

  - `backend/database.py`
    - Small SQLite helpers: stores events and photo metadata.
    - Functions used by `main.py` to record photos and list recent photos/events.

  - Virtualenv: `backend/venv/`
    - The project expects Picamera2 to be available to the Python process. On the Pi, `python3-picamera2` is installed system-wide; the venv is typically created with `--system-site-packages` so system packages are available from inside the venv.

- Frontend (directory: `PiDoorCam/`)
  - `index.html` - basic landing page / overview
  - `live.html` - Live view page. Embeds `/stream.mjpg` in an <img> tag and uses a WebSocket fallback to show slightly higher-fidelity frames. Has "Capture photo" and "Download replay" controls.
  - `photos.html` - Gallery of saved photos. Uses thumbnails if present (`data/photos/thumbs/`).
  - `heatmap.html`, `access.html`, `style.css`, `main.js` - site layout and behavior.

Data and runtime locations
--------------------------
- Saved photos: `backend/data/photos/`
- Thumbnails: `backend/data/photos/thumbs/`
- Sqlite DB: `backend/data/database.db` (or location as implemented in `backend/database.py`)
- Uvicorn pid/log: `/tmp/pidoorcam_uvicorn.pid` and `/tmp/pidoorcam_uvicorn.log`

How to run (quick)
------------------
On the Pi, from project root:

```bash
# (if you haven't provisioned) run setup.sh (may require sudo)
./setup.sh

# Start server (backgrounded by run.sh)
./run.sh

# Check server status (locally)
curl http://127.0.0.1:8080/live.html
curl http://127.0.0.1:8080/camera/frame -o /tmp/frame.jpg
# MJPEG stream
# open in browser or in an <img src="http://PI_IP:8080/stream.mjpg">
```

Network/access tips
-------------------
- If your browser says "site can't be reached":
  - Make sure your client (laptop/phone) is on the same network as the Pi.
  - Use the Pi's IP (example: `http://10.8.178.12:8080/live.html`). `hostname -I` on the Pi shows current IPs.
  - If `nc -vz PI_IP 8080` fails from your client, check Pi firewall (`ufw status`) or your router.
  - If the Pi's IP looks like a VPN address (e.g., `10.8.x.x`), the Pi might be on a VPN; disable it or use the LAN IP.

Quick troubleshooting for camera issues
--------------------------------------
- "Device or resource busy" in logs: some other process is using the camera. Common culprits:
  - `rpicam-hello` preview (stop with `pkill rpicam-hello`)
  - PipeWire/WirePlumber (stop user session services for testing)
  - Another uvicorn instance
- If you see a placeholder image on the page but the backend logs show an exception about Pillow/JPEG, check that `backend/camera.py` converts `RGBA` images to `RGB` before saving/encoding.
- If camera initialization keeps failing, reboot the Pi to clear the ISP pipeline state.

Developer notes / next steps
---------------------------
- Regenerating thumbnails: add a small script to iterate `backend/data/photos/` and create `thumbs/` for each saved photo.
- systemd service: there is a template `packaging/pidoorcam.service` (if present). Install it to run at boot.
- Auth: a simple API-key auth can be added to `backend/` to protect write endpoints.

Where to look when things break (quick map)
-------------------------------------------
- Server logs: `/tmp/pidoorcam_uvicorn.log`
- PID file: `/tmp/pidoorcam_uvicorn.pid`
- Camera code & buffer: `backend/camera.py`
- HTTP endpoints + WebSocket: `backend/main.py`
- Frontend UI: `PiDoorCam/live.html`, `PiDoorCam/photos.html`, `PiDoorCam/main.js`

That's it — keep this file handy and update it whenever you add features.

