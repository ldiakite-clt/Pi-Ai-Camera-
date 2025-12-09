
# Standard imports for file and time handling
import io
import os
import time
import uuid
from pathlib import Path
from typing import List

# Async and web stuff
import asyncio
import base64
import zipfile
from PIL import Image
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Local modules for DB, video, and camera
from . import database
from . import video_utils
from .rpicam_streaming import get_streamer, start_streamer, stop_streamer
from pathlib import Path
import io
from fastapi import BackgroundTasks

# Set up paths for where we keep the frontend and all our data
ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "PiDoorCam"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Fire up FastAPI (our web server)
app = FastAPI()



# This class keeps track of all the open WebSocket connections (for live updates)
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
        # Send a message to every connected client
        to_remove = []
        for ws in list(self.active):
            try:
                await ws.send_json(msg)
            except Exception:
                to_remove.append(ws)
        for ws in to_remove:
            self.disconnect(ws)


manager = ConnectionManager()




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
            
            # Always send detection results (even empty) so frontend can clear old boxes
            detection_msg = {
                "type": "detections",
                "detections": detections,
                "ts": int(time.time())
            }
            await manager.broadcast_json(detection_msg)
            
            # Check for person detection (75%+ confidence) and take action
            if detections:
                person_detections = [d for d in detections if d['class'] == 'person']
                person_count = len(person_detections)
                
                if person_count > 0:
                    current_time = time.time()
                    if (current_time - last_person_notification) > notification_cooldown:
                        best_detection = max(person_detections, key=lambda d: d.get('confidence', 0))
                        confidence = best_detection.get('confidence', 0.0)
                        snapshot_path = None
                        try:
                            # Validate frame is a JPEG
                            img = Image.open(io.BytesIO(frame))
                            img.verify()  # Raises if not a valid JPEG
                            # Save photo
                            photos_dir = DATA_DIR / "photos"

                            # This async function keeps sending frames and detection results to all connected clients
                            async def frame_broadcaster():
                                # We use rpicam-vid for both streaming and AI detection. One process, less headache.
                                streamer = get_streamer()
                                print("[frame_broadcaster] Using rpicam-vid for streaming + detection")

                                fps = 5  # How many frames per second we send to the browser
                                interval = 1.0 / fps

                                last_person_notification = 0
                                notification_cooldown = 3.0  # Don't spam notifications

                                while True:
                                    frame = streamer.get_frame()
                                    detections = streamer.get_detections() if streamer.is_running() else []

                                    if frame:
                                        # Send the frame as base64 to the frontend
                                        b64 = base64.b64encode(frame).decode('ascii')
                                        msg = {"type": "frame", "data": b64, "ts": int(time.time())}
                                        await manager.broadcast_json(msg)

                                        # Always send detection results, even if empty (so boxes clear)
                                        detection_msg = {
                                            "type": "detections",
                                            "detections": detections,
                                            "ts": int(time.time())
                                        }
                                        await manager.broadcast_json(detection_msg)

                                        # If we see a person, do some cool stuff
                                        if detections:
                                            person_detections = [d for d in detections if d['class'] == 'person']
                                            person_count = len(person_detections)

                                            if person_count > 0:
                                                current_time = time.time()
                                                if (current_time - last_person_notification) > notification_cooldown:
                                                    best_detection = max(person_detections, key=lambda d: d.get('confidence', 0))
                                                    confidence = best_detection.get('confidence', 0.0)
                                                    snapshot_path = None
                                                    try:
                                                        # Make sure the frame is a valid JPEG before saving
                                                        img = Image.open(io.BytesIO(frame))
                                                        img.verify()
                                                        # Save the photo
                                                        photos_dir = DATA_DIR / "photos"
                                                        photos_dir.mkdir(parents=True, exist_ok=True)
                                                        fname = f"detection-{int(current_time)}.jpg"
                                                        path = photos_dir / fname
                                                        with open(path, "wb") as fh:
                                                            fh.write(frame)
                                                        # Make a thumbnail for the gallery
                                                        thumbs_dir = photos_dir / "thumbs"
                                                        thumbs_dir.mkdir(parents=True, exist_ok=True)
                                                        try:
                                                            img = Image.open(io.BytesIO(frame))
                                                            img.thumbnail((300, 200))
                                                            thumb_path = thumbs_dir / fname
                                                            img.save(thumb_path, format="JPEG", quality=75)
                                                        except Exception:
                                                            pass  # If thumbnail fails, just skip it
                                                        # Add photo to the database
                                                        database.add_photo(int(current_time), str(path))
                                                        snapshot_path = f"/data/photos/{fname}"
                                                        print(f"[Detection] Auto-captured photo: {fname}")
                                                        # Tell the frontend a new photo was taken
                                                        await manager.broadcast_json({
                                                            "type": "event",
                                                            "name": "photo_taken",
                                                            "path": snapshot_path,
                                                            "thumb": f"/data/photos/thumbs/{fname}",
                                                            "ts": int(current_time)
                                                        })
                                                    except Exception as e:
                                                        print(f"[Detection] Error saving snapshot: {e}")

                                                    # Log the event for heatmap tracking
                                                    database.add_event(
                                                        timestamp=int(current_time),
                                                        label='person',
                                                        confidence=confidence,
                                                        snapshot_path=snapshot_path
                                                    )

                                                    # Send a notification to the frontend
                                                    notification_msg = {
                                                        "type": "notification",
                                                        "message": f"👤 Person detected ({int(confidence * 100)}% confidence)!",
                                                        "severity": "info",
                                                        "ts": int(current_time)
                                                    }
                                                    await manager.broadcast_json(notification_msg)
                                                    last_person_notification = current_time

                                                    # Log detection details to the server console
                                                    print(f"[Detection] Person detected at {time.strftime('%H:%M:%S')} - confidence={confidence:.0%}")
                                                    print(f"  - bbox={best_detection['bbox']}")
                                                    if snapshot_path:
                                                        print(f"  - Snapshot saved and added to heatmap")

                                    await asyncio.sleep(interval)

    path = photos_dir / fname
    with open(path, "wb") as fh:
        fh.write(frame)
    # generate a thumbnail to improve gallery load times
    thumbs_dir = photos_dir / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = None
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


@app.delete("/api/photos")
async def delete_all_photos():
    """Delete all photos and their files"""
    paths = database.delete_all_photos()
    deleted_count = 0
    
    photos_dir = DATA_DIR / "photos"
    thumbs_dir = photos_dir / "thumbs"
    
    for path in paths:
        try:
            photo_path = Path(path)
            if photo_path.exists():
                photo_path.unlink()
            # Delete thumbnail if exists
            thumb_path = thumbs_dir / photo_path.name
            if thumb_path.exists():
                thumb_path.unlink()
            deleted_count += 1
        except Exception as e:
            print(f"Error deleting photo file: {e}")
    
    await manager.broadcast_json({"type": "event", "name": "photos_cleared", "count": deleted_count})
    return JSONResponse({"success": True, "deleted": deleted_count})


@app.get("/api/events")
def get_events(limit: int = 100):
    rows = database.list_events(limit=limit)
    return JSONResponse(rows)


@app.delete("/api/events")
async def clear_all_events():
    """Clear all detection events (reset heatmap)"""
    deleted = database.clear_all_events()
    await manager.broadcast_json({"type": "event", "name": "events_cleared", "count": deleted})
    return JSONResponse({"success": True, "deleted": deleted})


@app.delete("/api/events/invalid")
async def clear_invalid_events():
    """Clear events without snapshots (old false positives)"""
    deleted = database.clear_events_without_snapshots()
    await manager.broadcast_json({"type": "event", "name": "invalid_events_cleared", "count": deleted})
    return JSONResponse({"success": True, "deleted": deleted})


@app.get("/api/heatmap")
def get_heatmap(days: int = 30):
    return JSONResponse(database.heatmap_last_days(days=days))


@app.get("/api/heatmap/photos")
def get_heatmap_photos(weekday: int, hour: int, days: int = 7, limit: int = 3, label: str = 'person'):
    """Get photos for a specific heatmap cell."""
    photos = database.get_heatmap_photos(weekday=weekday, hour=hour, days=days, limit=limit, label=label)
    return JSONResponse(photos)


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
async def create_replay(seconds: int = 30):
    """Create and save a replay as MP4 in background, return immediately with status"""
    if seconds <= 0 or seconds > 300:
        raise HTTPException(status_code=400, detail="seconds must be 1..300")
    
    streamer = get_streamer()
    
    # Quick check if buffer has any frames (non-blocking)
    if not streamer.is_running():
        raise HTTPException(status_code=503, detail="Camera not running")
    
    # Create replays directory
    replays_dir = DATA_DIR / "replays"
    replays_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    timestamp = int(time.time())
    filename = f"replay-{timestamp}-{seconds}s.mp4"
    output_path = replays_dir / filename
    
    # Run everything in background thread to avoid blocking
    async def encode_and_save():
        try:
            print(f"[replay] Background task started for {seconds}s replay", flush=True)
            
            # Get frames in background thread (holds lock briefly)
            frames = await asyncio.to_thread(streamer.get_recent_frames, seconds)
            if not frames:
                print("[replay] No frames available", flush=True)
                await manager.broadcast_json({
                    "type": "error",
                    "message": "No frames available for replay",
                    "ts": int(time.time())
                })
                return
            
            # Use the timestamp from the FIRST frame as the video start time
            # This ensures the displayed time matches the actual video content
            video_start_timestamp = frames[0][0]
            
            print(f"[replay] Got {len(frames)} frames, starting encode...", flush=True)
            
            # Run CPU-intensive FFmpeg encoding in thread pool
            # Use 15fps to match source camera framerate for real-time playback
            metadata = await asyncio.to_thread(
                video_utils.frames_to_mp4, frames, output_path, 15
            )
            
            # Save to database with the actual video start time
            replay_id = await asyncio.to_thread(
                database.add_replay,
                video_start_timestamp,
                metadata['duration'],
                metadata['frame_count'],
                metadata['file_size'],
                str(output_path)
            )
            
            # Cleanup old replays
            old_paths = await asyncio.to_thread(database.cleanup_old_replays, 100)
            for old_path in old_paths:
                try:
                    Path(old_path).unlink(missing_ok=True)
                except Exception:
                    pass
            
            # Broadcast completion
            await manager.broadcast_json({
                "type": "event",
                "name": "replay_saved",
                "id": replay_id,
                "duration": metadata['duration'],
                "path": f"/data/replays/{filename}",
                "ts": video_start_timestamp
            })
            print(f"[replay] Saved: {filename}", flush=True)
        except Exception as e:
            import traceback
            print(f"[replay] Error encoding: {e}", flush=True)
            traceback.print_exc()
            await manager.broadcast_json({
                "type": "error",
                "message": f"Replay encoding failed: {str(e)}",
                "ts": int(time.time())
            })
    
    # Start background task (non-blocking)
    asyncio.create_task(encode_and_save())
    
    # Return immediately with pending status
    return JSONResponse({
        "status": "encoding",
        "message": "Replay is being created in background",
        "filename": filename,
        "path": f"/data/replays/{filename}",
        "timestamp": timestamp,
        "seconds": seconds
    })


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
    
    return JSONResponse({"success": True, "id": replay_id})


@app.delete("/api/replays")
async def delete_all_replays():
    """Delete all replays and their files"""
    paths = database.delete_all_replays()
    deleted_count = 0
    
    for path in paths:
        try:
            replay_path = Path(path)
            if replay_path.exists():
                replay_path.unlink()
            deleted_count += 1
        except Exception as e:
            print(f"Error deleting replay file: {e}")
    
    await manager.broadcast_json({"type": "event", "name": "replays_cleared", "count": deleted_count})
    return JSONResponse({"success": True, "deleted": deleted_count})


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

# Mount frontend static files at /ui path (NOT "/" to avoid blocking API routes)
if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# Redirect root to frontend
@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/ui/index.html")


# Serve individual HTML pages at root level for convenience
@app.get("/{page}.html")
async def serve_html(page: str):
    from fastapi.responses import FileResponse
    html_path = FRONTEND_DIR / f"{page}.html"
    if html_path.exists():
        return FileResponse(html_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="Page not found")


# Serve CSS at root level
@app.get("/style.css")
async def serve_css():
    from fastapi.responses import FileResponse
    css_path = FRONTEND_DIR / "style.css"
    if css_path.exists():
        return FileResponse(css_path, media_type="text/css")
    raise HTTPException(status_code=404, detail="CSS not found")
