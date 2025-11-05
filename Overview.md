# AI Door Camera (Local Recognition) - Project Overview

## 1. PROJECT SUMMARY

- **Title:** AI Door Camera (Local Recognition)
- **Client:** Roommates in our apartment
- **Goal:** Identify who is at the door using a Raspberry Pi 5 + Pi AI Camera. Show a local web dashboard with last visitor, events timeline, and quiet-hours heatmap. No cloud.
- **Users:** 
  - All roommates (viewer)
  - Admin (me) for enrollment + settings
- **Privacy defaults:** 
  - Local-only
  - Snapshots enabled
  - ROI restricted to interior threshold

---

## 2. SITEMAP AND NAVIGATION

### Pages (top-bar nav):

- **Home** → `/index.html`
- **Events** → `/events.html`
- **Heatmap** → `/heatmap.html`
- **Enroll*** → `/enroll.html` *(admin only)*
- **Settings*** → `/settings.html` *(admin only)*
- **Help** → `/help.html`

---

## 3. PAGE-BY-PAGE SPECIFICATION

### A) Home (`/index.html`)

- **Purpose:** Live status + last visitor card
- **Audience:** Everyone
- **Data entry:** None
- **Controls:** 
  - Arm/Disarm (visible to all, only works if admin token present)
  - "Capture snapshot" button
- **Actions:** 
  - Open WebSocket
  - Render last event
  - Deep-link to Events and Heatmap

### B) Events (`/events.html`)

- **Purpose:** Review detections
- **Audience:** Everyone
- **Data entry:** Filter form (date range, label)
- **Validations:** start <= end
- **Controls:** 
  - Label dropdown
  - Date pickers
  - Export CSV
  - Load more
- **Actions:** 
  - Fetch `/api/events`
  - Click row → GET `/api/snapshot?id=...`

### C) Heatmap (`/heatmap.html`)

- **Purpose:** Visualize activity per hour × weekday
- **Audience:** Everyone
- **Data entry:** Optional label filter
- **Controls:** Dropdown with legend
- **Actions:** 
  - Fetch last 30 days
  - Bucket and draw

### D) Enroll (`/enroll.html`) *[admin]*

- **Purpose:** Add roommates
- **Audience:** Admin
- **Data entry:** 
  - Name (required, unique)
  - 8–12 images via webcam or upload
- **Validations:** 
  - Name non-empty
  - >=5 images
  - Exactly 1 face per image
- **Controls:** 
  - Name input
  - Open camera
  - Capture
  - Upload
  - Submit
- **Actions:** POST `/api/enroll`

### E) Settings (`/settings.html`) *[admin]*

- **Purpose:** Configure recognition + privacy
- **Audience:** Admin
- **Data entry:** 
  - Threshold (0.30..0.80)
  - ROI rectangle
  - Snapshots toggle
  - Armed toggle
- **Validations:** 
  - Numeric range
  - ROI within frame
- **Controls:** 
  - Number input
  - Checkbox
  - ROI canvas overlay
  - Save
- **Actions:** POST `/api/settings`

### F) Help (`/help.html`)

- **Purpose:** Explain how it works + privacy/consent
- **Audience:** Everyone
- **Data entry:** None
- **Controls:** Links to README and consent note

---

## 4. DYNAMIC JS FEATURES (TO BE IMPLEMENTED)

- WebSocket live updates on Home + Events
- Enrollment camera capture via `getUserMedia` in Enroll
- Heatmap drawing on `<canvas>` in Heatmap
- Filters + validation in Events (dates, label)
- Basic admin passcode gate for Enroll + Settings (front-end gate + backend check)

---

## 5. SIMPLE ADMIN PASSCODE (HOW IT WORKS)

### Front-end gate:
When opening `/enroll` or `/settings`, if no admin token in `localStorage`, show a passcode prompt overlay. On submit:
1. Call POST `/api/login {passcode}`
2. If backend returns ok, set `localStorage.adminToken = "1"` and continue
3. If not ok, stay locked

*Note: This only hides UI on the client; the backend must still enforce auth (e.g., require a session cookie on protected endpoints).*

### Backend enforcement (for later):
- `/api/login` issues an HttpOnly session cookie on success
- Protected routes check the cookie
- Front-end token is only for toggling UI

---

## 6. FRONTEND FOLDER STRUCTURE

```
frontend/
├── index.html
├── events.html
├── heatmap.html
├── enroll.html
├── settings.html
├── help.html
├── app.css
├── app.js
├── assets/
│   └── logo.svg
└── demo/
    └── demo_data.json
```

---

## 7. TECHNICAL IMPLEMENTATION GUIDE

### 7.1 System Architecture

**✅ Project Feasibility: YES - This is a well-established, practical architecture**

```
Pi AI Camera → Raspberry Pi 5 Backend
                    ↓
        [Video Processing Pipeline]
                    ↓
            ┌───────┴───────┐
            ↓               ↓
    Face Recognition    WebSocket Server
            ↓               ↓
        Database    ← → Web Clients
                        (Local WiFi)
```

### 7.2 Why This Project is Feasible

#### Hardware Capabilities:
- **Raspberry Pi 5** - Powerful enough for concurrent streaming + AI processing
- **Pi AI Camera Module** - Hardware-accelerated video encoding, supports multiple consumers
- **Local WiFi Network** - 100+ Mbps bandwidth, low latency (50-150ms)

#### Expected Performance:
- **Resolution:** 640x480 or 1280x720
- **FPS:** 15-25 fps for streaming (30 fps with single viewer)
- **Latency:** 200-500ms end-to-end
- **Concurrent Users:** 2-4 roommates comfortably

---

## 8. RECOMMENDED TECH STACK

### Backend (Python - Recommended)

```python
# Core Technologies:
Python 3.11+
├── FastAPI or Flask (async web framework)
├── python-socketio (WebSocket support)
├── picamera2 (Pi camera interface)
├── opencv-python (video encoding/processing)
├── face_recognition or deepface (AI recognition)
└── SQLite (event database - local, no setup needed)
```

**Why Python?**
- Native Pi camera support via picamera2
- Excellent face recognition libraries
- FastAPI provides async support for WebSocket
- Easy to develop and debug

### Frontend (Keep it Simple)

```javascript
Vanilla JavaScript (no framework overhead)
├── Socket.io-client (WebSocket client)
├── HTML5 <video> or <img> tags (video display)
└── Canvas API (ROI overlay, heatmap drawing)
```

**Why Vanilla JS?**
- No build process needed
- Works on all devices (phones, tablets, laptops)
- Faster loading on local network
- Easier for roommates to access

---

## 9. VIDEO STREAMING IMPLEMENTATION OPTIONS

### Option 1: MJPEG over WebSocket (RECOMMENDED FOR STARTING)

**Pros:**
- Simple to implement
- Works in all browsers via `<img>` tag
- Easy debugging (each frame is a JPEG)
- Lower latency than you'd expect
- Can adjust quality dynamically

**Cons:**
- Higher bandwidth than H.264
- Not as efficient for multiple viewers

**Implementation:**
```python
# Pseudo-code
while True:
    frame = camera.capture_array()
    _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    socketio.emit('frame', {'image': base64.b64encode(jpeg).decode()})
    time.sleep(1/25)  # 25 FPS
```

**Client:**
```javascript
socket.on('frame', (data) => {
    imgElement.src = 'data:image/jpeg;base64,' + data.image;
});
```

### Option 2: WebRTC (BEST QUALITY, MORE COMPLEX)

**Pros:**
- Built-in browser support
- Best latency (<200ms)
- Peer-to-peer capable
- Adaptive bitrate

**Cons:**
- More complex setup
- Requires STUN/TURN for some networks
- Harder to debug

**Use when:** You need multiple simultaneous viewers with low latency

### Option 3: HLS (HTTP Live Streaming)

**Pros:**
- Very stable
- Native `<video>` tag support
- Handles network issues well
- Can cache segments

**Cons:**
- Higher latency (2-5 seconds)
- Requires generating .m3u8 playlist + .ts chunks

**Use when:** Latency isn't critical, stability is priority

---

## 10. DEVELOPMENT PHASES

### Phase 1: Basic Web Server + Camera (Week 1)
- [ ] Set up FastAPI on Pi 5
- [ ] Get picamera2 capturing frames
- [ ] Serve static HTML files (index.html, etc.)
- [ ] Test camera preview in browser via MJPEG

### Phase 2: WebSocket Live Stream (Week 2)
- [ ] Implement Socket.io on backend
- [ ] Send frames over WebSocket
- [ ] Display live stream on `/live.html`
- [ ] Add FPS counter and latency monitor
- [ ] Test with 2-3 concurrent connections

### Phase 3: Face Recognition Pipeline (Week 3)
- [ ] Install face_recognition library
- [ ] Create enrollment system (capture 8-12 images per person)
- [ ] Build face database (embeddings stored in SQLite)
- [ ] Run detection at 1-2 FPS (lower than stream FPS)
- [ ] Display "Last Visitor" card on home page

### Phase 4: Events & Database (Week 4)
- [ ] Create SQLite schema (events table)
- [ ] Log detection events with timestamp, label, confidence
- [ ] Optionally save snapshot images
- [ ] Build `/api/events` endpoint with filtering
- [ ] Implement Events page with date/label filters

### Phase 5: Heatmap Visualization (Week 5)
- [ ] Query events for last 30 days
- [ ] Bucket by hour × weekday
- [ ] Draw heatmap on `<canvas>`
- [ ] Add color legend and label filter

### Phase 6: Admin Features (Week 6)
- [ ] Implement passcode login (`/api/login`)
- [ ] Protect `/enroll` and `/settings` routes
- [ ] Build enrollment UI (webcam capture via getUserMedia)
- [ ] Build settings UI (ROI canvas overlay, threshold slider)
- [ ] Add arm/disarm toggle

### Phase 7: Polish & Testing (Week 7)
- [ ] Test on all roommates' devices
- [ ] Optimize performance (frame skipping if needed)
- [ ] Add error handling and reconnection logic
- [ ] Write Help page documentation
- [ ] Set up auto-start on Pi boot (systemd service)

---

## 11. SECURITY & PRIVACY IMPLEMENTATION

### Network Security:

**Option A: Pi on Existing Home WiFi**
- Connect Pi to home router
- Access via local IP (e.g., `http://192.168.1.100:8000`)
- Router provides first layer of security (WPA2/3)

**Option B: Pi as WiFi Hotspot**
- Pi creates own WiFi network
- Roommates connect to "PiDoorCam" WiFi
- Full isolation from internet
- Requires second WiFi adapter or built-in WiFi

### Application Security:

1. **Session-based Authentication:**
   ```python
   # Backend enforces auth on protected routes
   @app.post("/api/login")
   async def login(passcode: str):
       if passcode == ADMIN_PASSCODE:
           session['admin'] = True
           return {"success": True}
   ```

2. **Frontend Token Gate:**
   ```javascript
   // Only hides UI, backend still checks
   if (!localStorage.getItem('adminToken')) {
       showPasscodePrompt();
   }
   ```

3. **HTTPS (Optional but Recommended):**
   - Generate self-signed certificate for local use
   - Or use mDNS + Let's Encrypt if you set up a local domain

### Privacy Defaults:

- ✅ **Local-only processing** (no cloud uploads)
- ✅ **ROI restricted to door area** (don't capture whole room)
- ✅ **Snapshots optional** (can be disabled in settings)
- ✅ **Unknown faces logged as "Unknown"** (no image saved unless enabled)
- ✅ **Event retention policy** (auto-delete events older than 90 days)

---

## 12. PERFORMANCE OPTIMIZATION STRATEGIES

### CPU Load Management:

**Problem:** Face recognition + video encoding can overload Pi 5

**Solution: Dual Frame Rate System**
```python
# Stream at 25 FPS
# Face recognition at 2 FPS (every 12th frame)

frame_count = 0
while True:
    frame = camera.capture()
    
    # Always stream
    send_to_websocket(frame)
    
    # Only recognize periodically
    if frame_count % 12 == 0:
        recognize_face(frame)
    
    frame_count += 1
```

### Bandwidth Optimization:

| Viewers | Resolution | Quality | Bandwidth/viewer |
|---------|-----------|---------|------------------|
| 1       | 1280x720  | 80%     | ~2 Mbps         |
| 2-3     | 640x480   | 70%     | ~800 Kbps       |
| 4+      | 640x480   | 60%     | ~500 Kbps       |

**Dynamic Quality Adjustment:**
```python
def get_quality(num_viewers):
    if num_viewers == 1:
        return {'width': 1280, 'height': 720, 'quality': 80}
    elif num_viewers <= 3:
        return {'width': 640, 'height': 480, 'quality': 70}
    else:
        return {'width': 640, 'height': 480, 'quality': 60}
```

### Memory Management:

- Use `numpy` arrays efficiently (avoid copies)
- Limit event database to last 90 days
- Compress snapshot images (JPEG quality 60-70)
- Delete embeddings for un-enrolled users

---

## 13. POWER & HARDWARE REQUIREMENTS

### Essential Hardware:

- ✅ **Raspberry Pi 5** (4GB or 8GB RAM)
- ✅ **Pi AI Camera Module**
- ✅ **Official 27W USB-C Power Supply** (5V/5A - CRITICAL!)
- ✅ **32GB+ microSD card** (Class 10 or better)
- ✅ **Ethernet cable** (optional, for stable connection during setup)

### Optional but Recommended:

- 🔌 **UPS/Battery backup** (keep running during power outages)
- 🌡️ **Heatsink/Fan** (Pi 5 can get hot under load)
- 💾 **External SSD** (faster than microSD, longer lifespan)

### Power Consumption Notes:

- Pi 5 under load: 5-8W
- Idle: 3-4W
- 24/7 operation: ~$2-4/month electricity (USA average)

---

## 14. DEVELOPMENT ENVIRONMENT SETUP

### On Raspberry Pi 5:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11+
sudo apt install python3-pip python3-venv -y

# Install system dependencies
sudo apt install libcamera-dev libopencv-dev -y

# Create project directory
mkdir ~/ai-door-camera
cd ~/ai-door-camera

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install fastapi uvicorn python-socketio picamera2 opencv-python face-recognition aiofiles
```

### Testing Locally:

```bash
# Start development server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Access from laptop on same network
# http://<pi-ip-address>:8000
```

---

## 15. PROJECT FILE STRUCTURE (FULL STACK)

```
ai-door-camera/
├── backend/
│   ├── main.py                 # FastAPI app entry point
│   ├── camera.py               # Camera capture logic
│   ├── recognition.py          # Face recognition pipeline
│   ├── database.py             # SQLite operations
│   ├── websocket.py            # WebSocket handlers
│   ├── models/
│   │   ├── events.py           # Event data model
│   │   └── settings.py         # Settings data model
│   ├── routes/
│   │   ├── api.py              # REST API endpoints
│   │   └── auth.py             # Authentication
│   └── data/
│       ├── embeddings/         # Face embeddings
│       ├── snapshots/          # Event snapshots
│       └── database.db         # SQLite database
├── frontend/
│   ├── index.html              # Home page
│   ├── events.html             # Events log
│   ├── heatmap.html            # Activity heatmap
│   ├── enroll.html             # Enrollment (admin)
│   ├── settings.html           # Settings (admin)
│   ├── help.html               # Help/documentation
│   ├── app.css                 # Global styles
│   ├── app.js                  # Shared utilities
│   └── assets/
│       └── logo.svg
├── venv/                       # Python virtual environment
├── requirements.txt            # Python dependencies
├── README.md                   # Project documentation
├── Overview.md                 # This file
└── .gitignore                  # Git ignore rules
```

---

## 16. TROUBLESHOOTING GUIDE

### Common Issues & Solutions:

#### "Camera not detected"
```bash
# Check camera connection
libcamera-hello

# Enable camera in raspi-config
sudo raspi-config
# Interface Options -> Camera -> Enable
```

#### "WebSocket won't connect"
- Check firewall: `sudo ufw allow 8000`
- Verify Pi IP: `hostname -I`
- Test with curl: `curl http://<pi-ip>:8000`

#### "High CPU usage"
- Reduce face recognition FPS (run every 20th frame instead of 12th)
- Lower stream resolution to 640x480
- Reduce JPEG quality to 60%

#### "Latency too high"
- Switch from WiFi to Ethernet
- Reduce number of concurrent viewers
- Use WebRTC instead of MJPEG

#### "Face recognition inaccurate"
- Enroll more images per person (12 instead of 8)
- Adjust threshold in settings (try 0.50-0.60)
- Ensure good lighting at door
- Check ROI includes full face area

---

## 17. NEXT STEPS & GETTING STARTED

### Immediate Actions:

1. **Set up Pi 5:**
   - Install Raspberry Pi OS (64-bit)
   - Connect Pi AI Camera
   - Update system and install dependencies

2. **Clone Repository:**
   ```bash
   git clone https://github.com/ldiakite-clt/Pi-Ai-Camera-.git
   cd Pi-Ai-Camera-
   ```

3. **Test Camera:**
   ```bash
   libcamera-hello
   # Should show camera preview
   ```

4. **Start Development:**
   - Begin with Phase 1 (Basic Web Server + Camera)
   - Work through phases incrementally
   - Test each component before moving to next

### Resources & References:

- [Picamera2 Documentation](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Socket.io Documentation](https://socket.io/docs/v4/)
- [Face Recognition Library](https://github.com/ageitgey/face_recognition)

---

## 18. DEVELOPMENT WORKFLOW: PI vs LAPTOP

### ✅ RECOMMENDED: Use VSCode Remote-SSH from Laptop to Pi

**This is the BEST approach for this project!**

#### Why Work Remotely on Pi from Laptop:

**Pros:**
- ✅ **Test in real environment** - Camera is connected to Pi, not laptop
- ✅ **Same deployment target** - No "works on my laptop but not Pi" issues  
- ✅ **VSCode Remote-SSH is excellent** - Full IDE features on remote machine
- ✅ **Faster iteration** - No need to push/pull to test changes
- ✅ **Access Pi camera directly** - Can test face recognition immediately
- ✅ **Better resource usage** - Laptop keyboard/screen, Pi processing power
- ✅ **Keep laptop battery** - Pi is always on, laptop can sleep

**Cons:**
- ⚠️ Need SSH access to Pi (easy to set up)
- ⚠️ Both devices must be on same network
- ⚠️ Slight lag if WiFi is poor (use Ethernet)

#### Setup Instructions:

**1. Enable SSH on Pi:**
```bash
# On Pi directly (keyboard + monitor) or via raspi-config
sudo raspi-config
# Interface Options -> SSH -> Enable

# Or via command:
sudo systemctl enable ssh
sudo systemctl start ssh
```

**2. Get Pi's IP Address:**
```bash
# On Pi:
hostname -I
# Example output: 192.168.1.100
```

**3. Install VSCode Remote-SSH Extension on Laptop:**
- Open VSCode on your laptop
- Go to Extensions (Ctrl+Shift+X)
- Search "Remote - SSH"
- Install extension by Microsoft

**4. Connect to Pi from Laptop:**
```
# In VSCode:
1. Press F1 or Ctrl+Shift+P
2. Type "Remote-SSH: Connect to Host"
3. Enter: pi@192.168.1.100 (use your Pi's IP)
4. Enter password when prompted
5. VSCode will reload and connect to Pi
```

**5. Open Project on Pi:**
```
# After connected via Remote-SSH:
File -> Open Folder -> /home/pi/ai-door-camera
```

**6. Install Python Extension on Remote:**
- VSCode will prompt to install extensions on SSH host
- Install Python extension on the Pi

Now you're coding on Pi from your laptop! 🎉

#### Development Workflow:

```
Day-to-Day Work:
1. Open VSCode on laptop
2. Connect to Pi via Remote-SSH (saves recent connections)
3. Edit code directly on Pi
4. Run/test immediately (camera works!)
5. Git commit/push from Pi
6. Close laptop, Pi keeps running
```

---

## 19. ALTERNATIVE WORKFLOWS (NOT RECOMMENDED FOR THIS PROJECT)

### Option 2: Develop on Laptop, Deploy to Pi

**When to use:** Simple Python scripts without hardware dependencies

**Problems for THIS project:**
- ❌ Can't test camera on laptop
- ❌ Can't test face recognition in real lighting
- ❌ Need to mock camera for local testing
- ❌ Push/pull cycle slows iteration
- ❌ Different ARM vs x86 architecture can cause issues

### Option 3: Develop Directly on Pi (Monitor + Keyboard)

**When to use:** No laptop available, or prefer traditional setup

**Problems:**
- ❌ Need extra monitor, keyboard, mouse for Pi
- ❌ Pi desktop environment is slower
- ❌ Smaller screen real estate
- ❌ Less comfortable for long coding sessions

---

## 20. BEST PRACTICES FOR REMOTE DEVELOPMENT

### Performance Tips:

**Use .gitignore to exclude large files:**
```gitignore
# Don't sync these over SSH
venv/
__pycache__/
*.pyc
data/snapshots/
data/embeddings/
*.db
node_modules/
```

**Use SSH keys instead of password:**
```bash
# On laptop, generate key (if you don't have one):
ssh-keygen -t ed25519

# Copy to Pi:
ssh-copy-id pi@192.168.1.100

# Now connect without password!
```

**Set up static IP for Pi:**
```bash
# Edit dhcpcd.conf on Pi:
sudo nano /etc/dhcpcd.conf

# Add at bottom:
interface wlan0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1

# Reboot:
sudo reboot
```

Now Pi always has same IP = easier to connect!

### Git Workflow:

```bash
# On Pi (via Remote-SSH in VSCode):
git add .
git commit -m "Add face recognition pipeline"
git push origin main

# Work from laptop later:
# Just reconnect to Pi via Remote-SSH
# Changes are already there!
```

### Backup Strategy:

- 📂 Git repository (code backup)
- 💾 Periodic Pi SD card image (full system backup)
- ☁️ Optional: Sync `data/` folder to laptop weekly

---

## 21. FINAL RECOMMENDATION

### For THIS Project: **Use VSCode Remote-SSH**

**Reasoning:**
1. You NEED the Pi camera to test
2. Face recognition must be tested in real environment
3. WebSocket streaming needs real camera feed
4. Remote-SSH gives you best of both worlds
5. Industry-standard workflow for embedded development

**Timeline:**
- **Week 1-2:** Set up Remote-SSH, get camera working
- **Week 3-7:** Develop features incrementally on Pi
- **Ongoing:** Code on Pi, test immediately, push to GitHub

**Comfort Level:**
- If you're comfortable with SSH: Start with Remote-SSH immediately ✅
- If new to SSH: Spend 30 min setting it up, then enjoy smooth workflow

---

## 22. SUMMARY CHECKLIST

### Pre-Development:
- [ ] Raspberry Pi 5 purchased and set up
- [ ] Pi AI Camera Module connected and tested
- [ ] SSH enabled on Pi
- [ ] Static IP configured for Pi
- [ ] VSCode Remote-SSH extension installed on laptop
- [ ] Successfully connected to Pi from laptop via Remote-SSH

### Phase 1 - Setup (This Week):
- [ ] Clone repository to Pi
- [ ] Install Python dependencies
- [ ] Test camera with `libcamera-hello`
- [ ] Get basic FastAPI server running
- [ ] Access server from laptop browser

### Development Approach:
- ✅ **Code on Pi via Remote-SSH from laptop**
- ✅ **Test with real camera immediately**
- ✅ **Push to GitHub from Pi**
- ✅ **Work incrementally through 7 phases**

**You're all set! This is a practical, achievable project. Start with Phase 1 and build from there.** 🚀
