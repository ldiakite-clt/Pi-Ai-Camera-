
"""
This file is the heart of our camera streaming and AI detection.
We use rpicam-vid for both MJPEG streaming and IMX500 person detection.
No need for separate processes—it's all in one place.
"""

import subprocess
import threading
import time
import json
from pathlib import Path
from typing import List, Dict, Optional
from collections import deque
import signal
import os


# List of COCO class names (for detection labels)
COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "", "backpack",
    "umbrella", "", "", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "", "wine glass", "cup", "fork", "knife", "spoon", "bowl",
    "banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza",
    "donut", "cake", "chair", "couch", "potted plant", "bed", "", "dining table", "", "",
    "toilet", "", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "", "book", "clock", "vase", "scissors",
    "teddy bear", "hair drier", "toothbrush"
]


class RPiCamStreaming:
    """
    This class wraps the rpicam-vid process for both MJPEG streaming and AI detection.
    We use stdout for MJPEG frames and a metadata file for detection results.
    """

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        framerate: int = 15,
        metadata_file: str = "/tmp/imx500_stream_detections.json"
    ):
        self.width = width
        self.height = height
        self.framerate = framerate
        self.metadata_file = Path(metadata_file)

        self._process: Optional[subprocess.Popen] = None
        self._running = False
        self._latest_detections: List[Dict] = []
        self._detection_lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None

        # Only count detections that show up in several frames (avoids false positives)
        self._detection_history: deque = deque(maxlen=5)  # Last 5 frames
        self._consecutive_person_frames = 0
        self._min_consecutive_frames = 3  # Require 3+ consecutive frames with person

        # MJPEG streaming state
        self._current_frame: Optional[bytes] = None
        self._frame_lock = threading.Lock()
        self._stream_thread: Optional[threading.Thread] = None

        # Buffer last 5 minutes of frames for replay (at 15fps = 4500 frames)
        self._frame_buffer = deque(maxlen=4500)
        self._buffer_lock = threading.Lock()

        print(f"[RPiCamStreaming] Initialized {width}x{height} @ {framerate}fps")
    
    def start(self):
        """Start rpicam-vid with MJPEG streaming and IMX500 detection."""
        if self._running:
            print("[RPiCamStreaming] Already running")
            return
        
        # Clean up old metadata
        if self.metadata_file.exists():
            self.metadata_file.unlink()
        
        # Use custom config WITHOUT object_detect_draw_cv (no boxes burned into stream)
        # The default /usr/share/rpi-camera-assets/imx500_mobilenet_ssd.json draws on video
        config_path = Path(__file__).resolve().parents[1] / "config" / "imx500_person_detection.json"
        
        # Build command: stream MJPEG to stdout, metadata to file
        cmd = [
            "rpicam-vid",
            "--post-process-file", str(config_path),
            "--width", str(self.width),
            "--height", str(self.height),
            "--framerate", str(self.framerate),
            "--nopreview",
            "--codec", "mjpeg",
            "--metadata", str(self.metadata_file),
            "--metadata-format", "json",
            "-t", "0",  # Run indefinitely
            "-o", "-",  # MJPEG to stdout
        ]
        
        print(f"[RPiCamStreaming] Starting rpicam-vid...")
        print(f"[RPiCamStreaming] Command: {' '.join(cmd)}")
        
        try:
            # Start subprocess
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )
            
            self._running = True
            
            # Start MJPEG frame reader thread
            self._stream_thread = threading.Thread(
                target=self._read_mjpeg_stream,
                daemon=True,
                name="RPiCam-MJPEGReader"
            )
            self._stream_thread.start()
            
            # Start metadata monitor thread
            self._monitor_thread = threading.Thread(
                target=self._monitor_metadata,
                daemon=True,
                name="RPiCam-MetadataMonitor"
            )
            self._monitor_thread.start()
            
            print(f"[RPiCamStreaming] Started (PID: {self._process.pid})")
            print("[RPiCamStreaming] Loading IMX500 firmware (this takes ~30 seconds)...")
            
        except Exception as e:
            print(f"[RPiCamStreaming] Failed to start: {e}")
            self._running = False
            raise
    
    def stop(self):
        """Stop rpicam-vid."""
        if not self._running:
            return
        
        print("[RPiCamStreaming] Stopping...")
        self._running = False
        
        # Kill process group
        if self._process:
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                self._process.wait(timeout=5)
                print("[RPiCamStreaming] Process terminated")
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                self._process.wait()
            except Exception as e:
                print(f"[RPiCamStreaming] Stop error: {e}")
        
        # Wait for threads
        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=2)
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2)
        
        # Cleanup
        if self.metadata_file.exists():
            self.metadata_file.unlink()
        
        print("[RPiCamStreaming] Stopped")
    
    def _read_mjpeg_stream(self):
        """Read MJPEG frames from stdout."""
        print("[RPiCamStreaming] MJPEG reader started")
        
        buffer = b""
        
        while self._running and self._process:
            try:
                chunk = self._process.stdout.read(4096)
                if not chunk:
                    break
                
                buffer += chunk
                
                # Look for JPEG boundaries
                while b"\xff\xd8" in buffer and b"\xff\xd9" in buffer:
                    start = buffer.find(b"\xff\xd8")
                    end = buffer.find(b"\xff\xd9", start) + 2
                    
                    if end > start:
                        frame = buffer[start:end]
                        buffer = buffer[end:]
                        
                        # Store frame
                        with self._frame_lock:
                            self._current_frame = frame
                        
                        # Add to buffer for replay
                        with self._buffer_lock:
                            self._frame_buffer.append((time.time(), frame))
                    else:
                        break
                        
            except Exception as e:
                if self._running:
                    print(f"[RPiCamStreaming] MJPEG read error: {e}")
                break
        
        print("[RPiCamStreaming] MJPEG reader stopped")
    
    def _monitor_metadata(self):
        """Monitor metadata file for detections."""
        print("[RPiCamStreaming] Metadata monitor started")
        
        last_position = 0
        firmware_loaded = False
        
        while self._running:
            try:
                if not self.metadata_file.exists():
                    time.sleep(0.1)
                    continue
                
                if not firmware_loaded:
                    print("[RPiCamStreaming] ✓ IMX500 firmware loaded!")
                    firmware_loaded = True
                
                # Read new content
                with open(self.metadata_file, 'r') as f:
                    f.seek(last_position)
                    new_content = f.read()
                    last_position = f.tell()
                
                if new_content.strip():
                    self._parse_metadata_content(new_content)
                
                time.sleep(0.1)
                
            except Exception as e:
                if self._running:
                    print(f"[RPiCamStreaming] Metadata monitor error: {e}")
                time.sleep(0.5)
        
        print("[RPiCamStreaming] Metadata monitor stopped")
    
    def _parse_metadata_content(self, content: str):
        """Parse metadata JSON."""
        try:
            lines = content.strip().split('\n')
            for line in lines:
                line = line.strip().rstrip(',')
                if not line or line == '[' or line == ']':
                    continue
                
                try:
                    frame_data = json.loads(line)
                    if isinstance(frame_data, dict):
                        self._extract_detections(frame_data)
                except json.JSONDecodeError:
                    continue
                    
        except Exception as e:
            pass
    
    def _extract_detections(self, frame_data: Dict):
        """Extract detections from metadata - MobileNet-SSD format."""
        try:
            if "CnnOutputTensor" not in frame_data:
                return
            
            tensor = frame_data["CnnOutputTensor"]
            if not tensor or len(tensor) < 600:  # Need at least bbox + conf + class data
                return
            
            # MobileNet-SSD tensor format (100 detections max):
            # [0-399]: bounding boxes (100 x 4 values: y1, x1, y2, x2)
            # [400-499]: confidence scores (100 values, 0.0-1.0)
            # [500-599]: class IDs (100 values, terminated by 100.0)
            
            NUM_DETECTIONS = 100
            BBOX_START = 0
            CONF_START = NUM_DETECTIONS * 4  # 400
            CLASS_START = CONF_START + NUM_DETECTIONS  # 500
            
            # Minimum confidence threshold for person detection
            # Model outputs low confidence for person, but we need some threshold
            # Combined with strict bbox size filtering to reduce false positives
            MIN_CONFIDENCE = 0.10
            
            detections = []
            debug_log = []
            
            for i in range(NUM_DETECTIONS):
                # Check if we have valid data
                class_val = tensor[CLASS_START + i] if CLASS_START + i < len(tensor) else None
                confidence = tensor[CONF_START + i] if CONF_START + i < len(tensor) else None
                bbox_idx = BBOX_START + (i * 4)
                y1 = tensor[bbox_idx] if bbox_idx < len(tensor) else None
                x1 = tensor[bbox_idx + 1] if bbox_idx + 1 < len(tensor) else None
                y2 = tensor[bbox_idx + 2] if bbox_idx + 2 < len(tensor) else None
                x2 = tensor[bbox_idx + 3] if bbox_idx + 3 < len(tensor) else None
                width = (x2 - x1) if (x2 is not None and x1 is not None) else None
                height = (y2 - y1) if (y2 is not None and y1 is not None) else None
                area = (width * height) if (width is not None and height is not None) else None
                
                debug_log.append(f"Detection {i}: class={class_val} conf={confidence} bbox=({x1},{y1},{x2},{y2}) w={width} h={height} area={area}")
                
                # 100.0 marks end of valid detections
                if class_val is None or class_val == 100.0:
                    break
                
                class_id = int(class_val)
                
                # ONLY detect persons (class_id 0)
                if class_id != 0:
                    continue
                
                # Get confidence for this detection
                if confidence is None or confidence < MIN_CONFIDENCE:
                    continue
                
                # Get bounding box (format: y1, x1, y2, x2)
                if None in (x1, y1, x2, y2):
                    continue
                
                # Validate bbox values are in range 0-1
                if not (0 <= x1 <= 1 and 0 <= y1 <= 1 and 0 <= x2 <= 1 and 0 <= y2 <= 1):
                    continue
                
                # Ensure proper ordering (x2 > x1, y2 > y1)
                if x2 <= x1 or y2 <= y1:
                    continue
                
                # Calculate width and height
                width = x2 - x1
                height = y2 - y1
                
                # Filter tiny detections (noise) - require reasonable person-sized bbox
                # Model outputs low confidence for person, so we rely on size filtering
                # A real person should take up significant frame space
                # Width can be narrow (5%) for partial/side views, but height should be 20%+
                if width < 0.05 or height < 0.20:
                    continue
                
                # Require at least 4% of frame area
                # This filters out small noise boxes that pass width/height checks
                area = width * height
                if area < 0.04:
                    continue
                
                detections.append({
                    'class': 'person',
                    'class_id': 0,
                    'confidence': round(confidence, 2),
                    'bbox': [round(x1, 3), round(y1, 3), round(x2, 3), round(y2, 3)]
                })
            
            # Apply temporal filtering: only report detections if consistent across frames
            has_person = len(detections) > 0
            self._detection_history.append(has_person)
            
            if has_person:
                self._consecutive_person_frames += 1
            else:
                self._consecutive_person_frames = 0
            
            print(f"[Detection] Frame: {len(detections)} person(s) detected. Consecutive: {self._consecutive_person_frames}")
            for log_entry in debug_log:
                print(f"[Detection] {log_entry}")
            
            # Only report detections if we have consistent detection across multiple frames
            # This prevents single-frame false positives
            with self._detection_lock:
                if self._consecutive_person_frames >= self._min_consecutive_frames:
                    self._latest_detections = detections
                else:
                    # Not enough consistent frames yet, report empty
                    self._latest_detections = []
                    
        except Exception as e:
            print(f"[Detection] Error parsing tensor: {e}")
    
    def get_frame(self) -> Optional[bytes]:
        """Get latest JPEG frame."""
        with self._frame_lock:
            return self._current_frame
    
    def get_detections(self) -> List[Dict]:
        """Get latest detections."""
        with self._detection_lock:
            return self._latest_detections.copy()
    
    def get_recent_frames(self, seconds: int) -> List[tuple]:
        """Get frames from the last N seconds as (timestamp, jpeg_bytes) tuples."""
        cutoff_time = time.time() - seconds
        frames = []
        
        with self._buffer_lock:
            for timestamp, frame in self._frame_buffer:
                if timestamp >= cutoff_time:
                    # Return as (timestamp_int, jpeg_bytes) tuple
                    frames.append((int(timestamp), frame))
        
        return frames
    
    def is_running(self) -> bool:
        """Check if running."""
        return self._running and self._process is not None and self._process.poll() is None


# Global instance
_streamer: Optional[RPiCamStreaming] = None


def get_streamer() -> RPiCamStreaming:
    """Get global streamer instance."""
    global _streamer
    if _streamer is None:
        _streamer = RPiCamStreaming()
    return _streamer


def start_streamer():
    """Start global streamer."""
    streamer = get_streamer()
    if not streamer.is_running():
        streamer.start()


def stop_streamer():
    """Stop global streamer."""
    global _streamer
    if _streamer:
        _streamer.stop()
        _streamer = None
