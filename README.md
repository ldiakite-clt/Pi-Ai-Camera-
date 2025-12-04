# Pi-Ai-Camera 🎥🤖

Raspberry Pi 5 security camera with IMX500 AI object detection.

## Features

- **🎥 Live Streaming**: Real-time MJPEG video feed via WebSocket
- **🤖 AI Object Detection**: IMX500 hardware-accelerated detection (80 COCO classes)
- **👤 Person Detection**: Toast notifications when people are detected
- **📸 Photo Gallery**: Save snapshots with thumbnails
- **⏪ Replay**: Save last 30 seconds as MP4 video
- **📊 Activity Heatmap**: Visualize detection patterns
- **🎨 Modern UI**: Glassmorphism design with responsive layout

## Hardware

- Raspberry Pi 5 (4-8GB RAM)
- Sony IMX500 AI Camera Module
- MicroSD Card (64GB+ recommended)

## Software Stack

### Backend
- **FastAPI**: REST API and WebSocket server
- **rpicam-vid**: Official camera interface with IMX500 support
- **Picamera2**: Python camera library (legacy support)
- **SQLite**: Photo and event database

### Frontend
- **Vanilla JavaScript**: No framework dependencies
- **WebSocket**: Real-time frame and detection streaming
- **Canvas API**: Bounding box rendering

### AI/ML
- **IMX500 ISP**: On-chip neural network accelerator
- **MobileNet-SSD**: Pre-trained object detection model
- **80 COCO Classes**: Person, car, bicycle, dog, cat, etc.

## Installation

### 1. Clone Repository
```bash
cd /home/thela/Desktop
git clone https://github.com/ldiakite-clt/Pi-Ai-Camera-.git
cd Pi-Ai-Camera-
```

### 2. Install Dependencies
```bash
# System packages
sudo apt update
sudo apt install -y python3-picamera2 python3-opencv python3-fastapi python3-uvicorn

# Python packages
pip3 install --upgrade picamera2 opencv-python fastapi uvicorn websockets pillow
```

### 3. IMX500 Setup (Optional)
If you encounter IMX500 compatibility issues with Python 3.13:
```bash
./install_picamera2_imx500_fix.sh
```

### 4. Start Backend
```bash
./run.sh
```

Access the UI at: `http://<raspberry-pi-ip>:8080`

## Usage

### Verify System
After SSH login, run the verification script:
```bash
cd /home/thela/Desktop/Pi-Ai-Camera-
./verify_system.sh
```

### Access Web Interface
- **Live Stream**: `http://100.84.75.9:8080/live.html`
- **Photos**: `http://100.84.75.9:8080/photos.html`
- **Replays**: `http://100.84.75.9:8080/replays.html`
- **Heatmap**: `http://100.84.75.9:8080/heatmap.html`

### API Endpoints

#### Camera
- `GET /camera/frame` - Get single JPEG frame
- `GET /stream.mjpg` - MJPEG stream
- `WS /ws` - WebSocket for live frames + detections

#### Photos
- `POST /api/photo` - Take photo
- `GET /api/photos` - List all photos
- `DELETE /api/photo/{id}` - Delete photo

#### Replays
- `POST /api/replay?seconds=30` - Save replay
- `GET /api/replays` - List all replays
- `DELETE /api/replay/{id}` - Delete replay

#### Analytics
- `GET /api/events` - List detection events
- `GET /api/heatmap?days=30` - Get activity heatmap

## Architecture

### Unified rpicam-vid Approach
```
┌─────────────────┐
│   rpicam-vid    │ (Single process)
│   + IMX500 ISP  │
└────────┬────────┘
         ├─→ MJPEG stdout ──→ FastAPI WebSocket
         └─→ JSON metadata ──→ Detection Parser
```

**Why rpicam-vid?**
- ✅ Official Raspberry Pi support
- ✅ Stable IMX500 firmware loading
- ✅ Low CPU usage (<5%)
- ✅ No Python threading issues
- ✅ Production-ready

**Alternative: Picamera2** (archived in `backend/ai_camera.py`)
- ❌ Race conditions with IMX500 firmware
- ❌ Python 3.13 compatibility issues
- ❌ Not recommended for AI features

## Detection Classes (COCO)

The IMX500 detects 80 object classes:
- **People**: person
- **Vehicles**: bicycle, car, motorcycle, airplane, bus, train, truck, boat
- **Animals**: bird, cat, dog, horse, sheep, cow, elephant, bear, zebra, giraffe
- **Household**: chair, couch, bed, dining table, toilet, tv, laptop, mouse, keyboard
- **Food**: banana, apple, sandwich, orange, pizza, donut, cake
- And 55+ more...

## Performance

- **Frame Rate**: 15 fps (streaming) + 30 fps (detection)
- **Latency**: <100ms WebSocket delivery
- **Detection Time**: ~33ms per frame (IMX500 hardware)
- **CPU Usage**: 3-5% (rpicam-vid) + 10-15% (FastAPI)
- **Memory**: ~150MB total
- **Startup Time**: ~30 seconds (IMX500 firmware loading)

## Configuration

### Camera Settings
Edit `backend/rpicam_streaming.py`:
```python
width = 640          # Resolution width
height = 480         # Resolution height
framerate = 15       # FPS for streaming
confidence = 0.55    # Detection threshold (0.0-1.0)
```

### Detection Settings
Edit `/usr/share/rpi-camera-assets/imx500_mobilenet_ssd.json`:
```json
{
  "threshold": 0.6,        // Confidence threshold
  "max_detections": 5,     // Max objects per frame
  "temporal_filter": true  // Smooth detections over time
}
```

## Troubleshooting

### Backend won't start
```bash
# Check for port conflicts
sudo lsof -i :8080

# Check logs
tail -f /tmp/backend.log
```

### IMX500 not detected
```bash
# Verify camera connection
libcamera-hello --list-cameras

# Should show: "imx500" in the output
```

### Python 3.13 errors
```bash
# Run the compatibility fix
./install_picamera2_imx500_fix.sh

# Or manually downgrade Picamera2
pip3 install picamera2==0.3.30
```

### Camera busy error
```bash
# Only one process can use camera at a time
pkill rpicam-vid
pkill -f uvicorn

# Restart
./run.sh
```

## File Structure

```
Pi-Ai-Camera-/
├── backend/
│   ├── main.py                  # FastAPI application
│   ├── rpicam_streaming.py      # Unified camera (rpicam-vid)
│   ├── object_detection.py      # COCO classes
│   ├── camera.py                # Picamera2 wrapper (legacy)
│   ├── database.py              # SQLite operations
│   └── video_utils.py           # MP4 generation
├── PiDoorCam/                   # Frontend
│   ├── index.html               # Home page
│   ├── live.html                # Live stream + detections
│   ├── photos.html              # Photo gallery
│   ├── replays.html             # Saved replays
│   ├── heatmap.html             # Activity heatmap
│   └── style.css                # Glassmorphism UI
├── data/
│   ├── photos/                  # Saved images
│   ├── replays/                 # MP4 videos
│   └── database.db              # SQLite database
├── run.sh                       # Start backend
├── verify_system.sh             # System check script
└── README.md                    # This file
```

## Development

### Adding New Detection Classes
1. Edit `backend/object_detection.py`
2. Add class name to `COCO_CLASSES` list
3. Update frontend filtering in `PiDoorCam/live.html`

### Customizing UI
- **Colors**: Edit CSS variables in `PiDoorCam/style.css`
- **Bounding Boxes**: Modify `drawDetections()` in `live.html`
- **Notifications**: Adjust `showToast()` parameters

### API Integration
```python
import requests

# Get latest frame
response = requests.get('http://100.84.75.9:8080/camera/frame')
with open('frame.jpg', 'wb') as f:
    f.write(response.content)

# Take photo
response = requests.post('http://100.84.75.9:8080/api/photo')
print(response.json())  # {'path': '/data/photos/...', 'ts': 1234567890}
```

## Known Issues

1. **Replay temporarily unavailable**: Frame buffering needs implementation with rpicam-vid
2. **Bounding boxes at [0,0,0,0]**: Coordinate extraction from CnnOutputTensor needs refinement
3. **~30s startup delay**: IMX500 firmware upload time (hardware limitation)

## Future Enhancements

- [ ] Face recognition (enroll roommates)
- [ ] Motion-triggered recording
- [ ] Cloud backup integration
- [ ] Mobile app
- [ ] Multi-camera support
- [ ] Custom AI models (pose detection, behavior analysis)

## License

MIT License - See LICENSE file for details

## Credits

- **Hardware**: Raspberry Pi Foundation
- **IMX500**: Sony Semiconductor Solutions
- **Camera Software**: Raspberry Pi rpicam-apps team
- **AI Model**: TensorFlow MobileNet-SSD (COCO dataset)

## Support

For issues or questions:
1. Check `./verify_system.sh` output
2. Review logs: `tail -f /tmp/backend.log`
3. GitHub Issues: https://github.com/ldiakite-clt/Pi-Ai-Camera-/issues

---

**Built with ❤️ on Raspberry Pi 5**
