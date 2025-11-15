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
from . import database
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


async def frame_broadcaster():
    cam = get_global_camera()
    # target fps for websocket frames
    fps = 5
    interval = 1.0 / fps
    while True:
        frame = cam.get_frame()
        if frame:
            b64 = base64.b64encode(frame).decode('ascii')
            msg = {"type": "frame", "data": b64, "ts": int(time.time())}
            await manager.broadcast_json(msg)
        await asyncio.sleep(interval)


@app.on_event("startup")
async def startup_event():
    # kick off background broadcaster
    asyncio.create_task(frame_broadcaster())


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
    cam = get_global_camera()
    frame = cam.get_frame()
    return StreamingResponse(io.BytesIO(frame), media_type="image/jpeg")


@app.post("/api/photo")
async def take_photo(background: BackgroundTasks):
    cam = get_global_camera()
    frame = cam.get_frame()
    if not frame:
        raise HTTPException(status_code=500, detail="no frame")
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


@app.get("/api/replay")
def replay(seconds: int = 30):
    if seconds <= 0 or seconds > 300:
        raise HTTPException(status_code=400, detail="seconds must be 1..300")
    cam = get_global_camera()
    frames = cam.get_recent_frames(seconds)
    if not frames:
        raise HTTPException(status_code=404, detail="no frames available")
    # create in-memory zip of frames
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, mode="w") as zf:
        for ts, jpeg in frames:
            name = f"frame-{ts}.jpg"
            zf.writestr(name, jpeg)
    bio.seek(0)
    return StreamingResponse(bio, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=replay-{seconds}s.zip"})


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


# Mount frontend static files last so API routes take precedence
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
