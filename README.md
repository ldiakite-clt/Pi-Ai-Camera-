# Pi-Ai-Camera Deployment Summary (December 8, 2025)

This project was for my Front-End Web Development class. It is a Raspberry Pi camera setup that uses AI to detect people, supports live viewing, photo capture, and short video clips ("replays"). Accesible via simple website on local network, as well as Tailscale VPN.

GitHub: https://github.com/ldiakite-clt/Pi-Ai-Camera-  
Branch: `main`

## What's in the backend

- `main.py`  
  Runs the web server and handles all requests. Streams live video, takes photos, and saves replays.

- `rpicam_streaming.py`  
  Interfaces with the camera and runs AI person detection. Streams video and detects people in real time.

- `database.py`  
  Stores metadata for photos, events, and replays using SQLite.

- `video_utils.py`  
  Builds MP4 replay clips from image frames using `ffmpeg` (used for the replay feature).

- `requirements.txt`  
  Python dependencies.

Note: Other files are old or for reference. The main system uses `rpicam-vid` for everything now.

## What's in the frontend

- `PiDoorCam/`  
  Website pages and styles:
  - `live.html`: Live view, take photos, save replays
  - `photos.html`: View and delete photos
  - `replays.html`: Download and delete replay clips
  - `heatmap.html`: Shows when/where motion happened
  - `style.css`: Site-wide styling

## How to use it

1. I SSH into Pi and open the project folder:
   ```bash
   cd /home/thela/Desktop/Pi-Ai-Camera-

2. ./verify_system.sh

3. pkill -f uvicorn
./run.sh
