#!/bin/bash
# Quick verification script for Pi-Ai-Camera after SSH login

echo "========================================"
echo "Pi-Ai-Camera System Verification"
echo "========================================"
echo ""

# Check repository
echo "📁 Repository Status:"
cd /home/thela/Desktop/Pi-Ai-Camera-
git status --short
echo "Latest commit: $(git log -1 --oneline)"
echo ""

# Check backend files
echo "🐍 Backend Python Files:"
ls -lh backend/*.py | awk '{print $9, "(" $5 ")"}'
echo ""

# Check if backend is running
echo "🚀 Backend Service:"
if pgrep -f "uvicorn" > /dev/null; then
    echo "✅ Backend is RUNNING (PID: $(pgrep -f uvicorn))"
    echo "   URL: http://$(hostname -I | awk '{print $1}'):8080"
else
    echo "❌ Backend is NOT running"
    echo "   Start with: cd /home/thela/Desktop/Pi-Ai-Camera- && ./run.sh"
fi
echo ""

# Check rpicam-vid
echo "🎥 Camera Process:"
if pgrep -f "rpicam-vid" > /dev/null; then
    echo "✅ rpicam-vid is RUNNING (PID: $(pgrep -f rpicam-vid))"
    METADATA_FILE="/tmp/imx500_stream_detections.json"
    if [ -f "$METADATA_FILE" ]; then
        SIZE=$(du -h "$METADATA_FILE" | cut -f1)
        echo "   Metadata file: $SIZE"
    fi
else
    echo "❌ rpicam-vid is NOT running"
fi
echo ""

# Check network access
echo "🌐 Network Access:"
echo "   Tailscale: http://100.84.75.9:8080"
echo "   Local: http://$(hostname -I | awk '{print $1}'):8080"
echo ""

# Check data directories
echo "📊 Data Directories:"
echo "   Photos: $(ls data/photos/*.jpg 2>/dev/null | wc -l) images"
echo "   Replays: $(ls data/replays/*.mp4 2>/dev/null | wc -l) videos"
echo ""

echo "========================================"
echo "Quick Links:"
echo "  Live Stream: http://100.84.75.9:8080/live.html"
echo "  Photos: http://100.84.75.9:8080/photos.html"
echo "  Replays: http://100.84.75.9:8080/replays.html"
echo "========================================"
