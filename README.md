#================================================================================
# Pi-Ai-Camera README - December 8, 2025
#================================================================================
#
# Here’s a plain summary of the Pi-Ai-Camera project:
#
#
# Backend files:
# main.py: Runs the FastAPI server, handles camera, photos, replays, and browser stuff.
# rpicam_streaming.py: Connects to the Pi camera, streams video, and does person detection.
# database.py: Tracks photos, events, and replays using SQLite.
# video_utils.py: Makes MP4 videos from images for replays.
# requirements.txt: Python packages you need.
#
# Frontend:
# All the HTML files for the web interface are in PiDoorCam/ (live view, gallery, replays, heatmap, etc.).
# style.css for the look.
#
# How to check if it’s working:
# Run verify_system.sh to see what’s running and what files are there.
# Run test_clone_access.sh to make sure you can clone and use the repo anywhere.
#
# Current Status:
# Server is running (Uvicorn + FastAPI)
# Camera process is up (rpicam-vid, IMX500 firmware loaded)
# You can get to it on your local network at: http://<your-pi-ip>:8080
# Photos and replays are saved in the data/ folder
#
# How to use it:
# 1. SSH into your Pi
# 2. Go to the project folder: cd /home/thela/Pi-Ai-Camera-
# 3. Pull any new changes: git pull origin main
# 4. Activate Python: source backend/venv/bin/activate
# 5. Start the server: uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
# 6. Open the web UI in your browser
#
# How it works:
# The Pi camera streams video and runs AI to spot people.
# You can take photos or save short video clips (replays) from the web page.
# Everything is saved so you can look back at events or download clips.
#
# Why this setup?
# It’s simple, works with official Pi stuff, and doesn’t use much CPU.
# No weird threading bugs.
# Easy to use and maintain.
#
# Everything is committed and pushed.
# If you ever need to check, just run the verification scripts or look at the README.
#
#================================================================================
# End of README
#================================================================================
