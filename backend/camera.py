import io
import time
from pathlib import Path
from typing import Optional, List, Tuple
from collections import deque

try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except Exception:
    PICAMERA2_AVAILABLE = False

from PIL import Image, ImageDraw, ImageFont


class Camera:
    def __init__(self, size=(640, 480)):
        self.size = size
        self._pc2 = None
        self._started = False
        # frame buffer for recent frames: deque of (ts, jpeg_bytes)
        self._buffer = deque()
        self._buffer_max_seconds = 300  # keep up to 5 minutes by default

        if PICAMERA2_AVAILABLE:
            try:
                self._pc2 = Picamera2()
                try:
                    self._pc2_config = self._pc2.create_preview_configuration(main={"size": self.size})
                except Exception:
                    # fallback to still config if preview config missing in this picamera2 version
                    self._pc2_config = self._pc2.create_still_configuration(main={"size": self.size})
                self._pc2.configure(self._pc2_config)
                self._pc2.start()
                self._started = True
            except Exception:
                # if anything fails, fall back to placeholder
                self._pc2 = None
                self._started = False

    def get_frame(self) -> bytes:
        """Return a JPEG frame (bytes). If camera not available, return a placeholder JPEG."""
        if self._pc2:
            try:
                array = self._pc2.capture_array()
                # convert numpy array to JPEG; handle different channel formats
                img = Image.fromarray(array)
                # JPEG doesn't support alpha; convert RGBA -> RGB
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                jpeg = buf.getvalue()
                # push into buffer with timestamp
                self._push_buffer(jpeg)
                return jpeg
            except Exception:
                jpeg = self._placeholder()
                self._push_buffer(jpeg)
                return jpeg
        jpeg = self._placeholder()
        self._push_buffer(jpeg)
        return jpeg

    def _push_buffer(self, jpeg: bytes) -> None:
        ts = int(time.time())
        self._buffer.append((ts, jpeg))
        # prune older than buffer_max_seconds
        cutoff = ts - self._buffer_max_seconds
        while self._buffer and self._buffer[0][0] < cutoff:
            self._buffer.popleft()

    def get_recent_frames(self, seconds: int) -> List[Tuple[int, bytes]]:
        """Return list of (ts, jpeg_bytes) for last `seconds` seconds."""
        if seconds <= 0:
            return []
        now = int(time.time())
        cutoff = now - seconds
        return [(ts, j) for (ts, j) in self._buffer if ts >= cutoff]

    def _placeholder(self) -> bytes:
        w, h = self.size
        img = Image.new("RGB", (w, h), color=(64, 64, 64))
        d = ImageDraw.Draw(img)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        text = f"No camera\n{ts}"
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        d.multiline_text((10, 10), text, fill=(200, 200, 200), font=font)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()


# singleton instance
_GLOBAL_CAMERA: Optional[Camera] = None


def get_global_camera() -> Camera:
    global _GLOBAL_CAMERA
    if _GLOBAL_CAMERA is None:
        _GLOBAL_CAMERA = Camera()
    return _GLOBAL_CAMERA
