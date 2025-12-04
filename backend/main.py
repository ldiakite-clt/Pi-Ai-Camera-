import io
import os
import time
import uuid
from pathlib import Path
from typing import List

import asyncio
import base64
import zipfile
from PIL import Image
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .camera import get_global_camera
from .ai_camera import get_global_ai_camera
from . import database
from . import video_utils
from .object_detection import ObjectDetector, COCO_CLASSES
from .rpicam_streaming import get_streamer, start_streamer, stop_streamer
from pathlib import Path
import io
from fastapi import BackgroundTasks

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "PiDoorCam"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()


# WebSocket manager
class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast_json(self, msg: dict):
        to_remove = []
        for ws in list(self.active):
            try:
                await ws.send_json(msg)
            except Exception:
                to_remove.append(ws)
        for ws in to_remove:
            self.disconnect(ws)


manager = ConnectionManager()

# Global object detector instance
_object_detector = None


def get_object_detector():
    global _object_detector
    if _object_detector is None:
        _object_detector = ObjectDetector(confidence_threshold=0.55)
    return _object_detector


async def frame_broadcaster():
    """
    Unified approach: rpicam-vid for both streaming and AI detection.
    Single process, more stable than hybrid.
    """
    streamer = get_streamer()
    
    print("[frame_broadcaster] Using rpicam-vid for streaming + detection")
    
    # target fps for websocket frames
    fps = 5
    interval = 1.0 / fps
    
    last_person_notification = 0
    notification_cooldown = 3.0  # seconds between person notifications
    
    while True:
        # Get streaming frame from rpicam-vid
        frame = streamer.get_frame()
        
        # Get detections from same rpicam-vid process
        detections = streamer.get_detections() if streamer.is_running() else []
        
        if frame:
            b64 = base64.b64encode(frame).decode('ascii')
            msg = {"type": "frame", "data": b64, "ts": int(time.time())}
            await manager.broadcast_json(msg)
            
            # Send detection results
            if detections:
                detection_msg = {
                    "type": "detections",
                    "detections": detections,
                    "ts": int(time.time())
                }
                await manager.broadcast_json(detection_msg)
                
                # Check for person detection and send notification
                person_count = sum(1 for d in detections if d['class'] == 'person')
                if person_count > 0:
                    current_time = time.time()
                    if (current_time - last_person_notification) > notification_cooldown:
                        notification_msg = {
                            "type": "notification",
                            "message": f"👤 {person_count} person{'s' if person_count > 1 else ''} detected!",
                            "severity": "info",
                            "ts": int(current_time)
                        }
                        await manager.broadcast_json(notification_msg)
                        last_person_notification = current_time
                        
                        # Log detection details
                        print(f"[Detection] {person_count} person(s) detected at {time.strftime('%H:%M:%S')}")
                        for det in [d for d in detections if d['class'] == 'person']:
                            print(f"  - Person: confidence={det['confidence']}, bbox={det['bbox']}")
        
        await asyncio.sleep(interval)


@app.on_event("startup")
async def startup_event():
    # Start unified rpicam-vid streamer
    print("[startup] Starting rpicam-vid streamer...")
    start_streamer()
    
    # kick off background broadcaster
    asyncio.create_task(frame_broadcaster())


@app.on_event("shutdown")
async def shutdown_event():
    # Stop rpicam-vid streamer
    print("[shutdown] Stopping rpicam-vid streamer...")
    stop_streamer()


def mjpeg_generator():
    cam = get_global_camera()
    boundary = b"--frame"
    while True:
        frame = cam.get_frame()
        if not frame:
            time.sleep(0.1)
            continue
        header = b"Content-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(frame)
        yield boundary + b"\r\n" + header + frame + b"\r\n"
        time.sleep(0.05)


@app.get("/stream.mjpg")
def stream_mjpg():
    return StreamingResponse(mjpeg_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/camera/frame")
def camera_frame():
    streamer = get_streamer()
    frame = streamer.get_frame()
    if not frame:
        raise HTTPException(status_code=503, detail="Camera not ready")
    return StreamingResponse(io.BytesIO(frame), media_type="image/jpeg")


@app.post("/api/photo")
async def take_photo(background: BackgroundTasks):
    streamer = get_streamer()
    frame = streamer.get_frame()
    if not frame:
        raise HTTPException(status_code=503, detail="Camera not ready")
    photos_dir = DATA_DIR / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    fname = f"photo-{int(time.time())}.jpg"
    path = photos_dir / fname
    with open(path, "wb") as fh:
        fh.write(frame)
    # generate a thumbnail to improve gallery load times
    thumbs_dir = photos_dir / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    try:
        img = Image.open(io.BytesIO(frame))
        img.thumbnail((300, 200))
        thumb_path = thumbs_dir / fname
        img.save(thumb_path, format="JPEG", quality=75)
    except Exception:
        # if thumbnail generation fails, continue without it
        thumb_path = None

    database.add_photo(int(time.time()), path)
    # push event to websockets
    await manager.broadcast_json({"type": "event", "name": "photo_taken", "path": f"/data/photos/{fname}", "ts": int(time.time())})
    return JSONResponse({"path": f"/data/photos/{fname}", "thumb": (f"/data/photos/thumbs/{fname}" if thumb_path else None), "ts": int(time.time())})


@app.get("/api/photos")
def list_photos():
    rows = database.list_photos(limit=500)
    # normalize stored filesystem path to public URLs and include thumbnail if present
    out = []
    for r in rows:
        p = r.get('path')
        fname = None
        try:
            from pathlib import Path as _P
            fname = _P(p).name
        except Exception:
            fname = None
        public = f"/data/photos/{fname}" if fname else p
        thumb = f"/data/photos/thumbs/{fname}" if fname else None
        out.append({"id": r.get('id'), "timestamp": r.get('timestamp'), "path": public, "thumb": thumb})
    return JSONResponse(out)


@app.delete("/api/photo/{photo_id}")
async def delete_photo(photo_id: int):
    path = database.delete_photo(photo_id)
    if not path:
        raise HTTPException(status_code=404, detail="Photo not found")
    
    # Delete the actual files (photo and thumbnail)
    try:
        photo_path = Path(path)
        if photo_path.exists():
            photo_path.unlink()
        
        # Delete thumbnail if it exists
        photos_dir = DATA_DIR / "photos"
        thumbs_dir = photos_dir / "thumbs"
        thumb_path = thumbs_dir / photo_path.name
        if thumb_path.exists():
            thumb_path.unlink()
    except Exception as e:
        # Log error but still return success since DB entry is deleted
        print(f"Error deleting files: {e}")
    
    # Broadcast deletion event to websockets
    await manager.broadcast_json({"type": "event", "name": "photo_deleted", "id": photo_id})
    return JSONResponse({"success": True, "id": photo_id})


@app.get("/api/events")
def get_events(limit: int = 100):
    rows = database.list_events(limit=limit)
    return JSONResponse(rows)


@app.get("/api/heatmap")
def get_heatmap(days: int = 30):
    return JSONResponse(database.heatmap_last_days(days=days))


@app.get("/data/enrollments/{eid}/{filename}")
def enroll_image(eid: str, filename: str):
    p = DATA_DIR / "enrollments" / eid / filename
    if not p.exists():
        raise HTTPException(status_code=404)
    return FileResponse(p)


@app.get("/data/photos/{filename}")
def photo_file(filename: str):
    p = DATA_DIR / "photos" / filename
    if not p.exists():
        raise HTTPException(status_code=404)
    return FileResponse(p)


@app.post("/api/replay")
async def create_replay(seconds: int = 30, background: BackgroundTasks = None):
    """Create and save a replay as MP4, then return for download"""
    if seconds <= 0 or seconds > 300:
        raise HTTPException(status_code=400, detail="seconds must be 1..300")
    # Note: Replay functionality needs frame buffering in rpicam_streaming
    # For now, disable this feature
    raise HTTPException(status_code=503, detail="Replay temporarily unavailable with rpicam-vid")
    
    # Create replays directory
    replays_dir = DATA_DIR / "replays"
    replays_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    timestamp = int(time.time())
    filename = f"replay-{timestamp}-{seconds}s.mp4"
    output_path = replays_dir / filename
    
    try:
        # Convert frames to MP4
        metadata = video_utils.frames_to_mp4(frames, output_path, fps=5)
        
        # Save to database
        replay_id = database.add_replay(
            timestamp=timestamp,
            duration=metadata['duration'],
            frame_count=metadata['frame_count'],
            file_size=metadata['file_size'],
            path=str(output_path)
        )
        
        # Cleanup old replays (keep last 100)
        old_paths = database.cleanup_old_replays(keep_count=100)
        for old_path in old_paths:
            try:
                Path(old_path).unlink(missing_ok=True)
            except Exception:
                pass
        
        # Broadcast event to websockets
        await manager.broadcast_json({
            "type": "event",
            "name": "replay_saved",
            "id": replay_id,
            "duration": metadata['duration'],
            "ts": timestamp
        })
        
        # Return file for download
        return FileResponse(
            output_path,
            media_type="video/mp4",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create replay: {str(e)}")


@app.get("/api/replays")
def list_replays():
    """List all saved replays"""
    rows = database.list_replays(limit=100)
    out = []
    for r in rows:
        p = r.get('path')
        fname = None
        try:
            fname = Path(p).name
        except Exception:
            fname = None
        public = f"/data/replays/{fname}" if fname else p
        out.append({
            "id": r.get('id'),
            "timestamp": r.get('timestamp'),
            "duration": r.get('duration'),
            "frame_count": r.get('frame_count'),
            "file_size": r.get('file_size'),
            "path": public
        })
    return JSONResponse(out)


@app.delete("/api/replay/{replay_id}")
async def delete_replay(replay_id: int):
    """Delete a replay by ID"""
    path = database.delete_replay(replay_id)
    if not path:
        raise HTTPException(status_code=404, detail="Replay not found")
    
    # Delete the actual file
    try:
        replay_path = Path(path)
        if replay_path.exists():
            replay_path.unlink()
    except Exception as e:
        print(f"Error deleting replay file: {e}")


@app.post("/api/test/person-detection")
async def test_person_detection():
    """Test endpoint to trigger a person detection notification"""
    notification_msg = {
        "type": "notification",
        "message": "👤 Test: Person detected!",
        "severity": "info",
        "ts": int(time.time())
    }
    await manager.broadcast_json(notification_msg)
    return {"status": "notification sent"}
    
    # Broadcast deletion event
    await manager.broadcast_json({"type": "event", "name": "replay_deleted", "id": replay_id})
    return JSONResponse({"success": True, "id": replay_id})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            # keep connection alive; optionally receive client pings
            data = await ws.receive_text()
            # ignore or handle pings
    except WebSocketDisconnect:
        manager.disconnect(ws)


# Mount data directory for serving photos and replays
if DATA_DIR.exists():
    app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")

# Mount frontend static files last so API routes take precedence
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
