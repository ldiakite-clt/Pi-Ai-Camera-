"""
Unified camera streaming and detection using rpicam-vid.
Replaces separate Picamera2 streaming + rpicam-vid detection.
"""

import subprocess
import threading
import time
import json
from pathlib import Path
from typing import List, Dict, Optional
import signal
import os

# COCO class names
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
    Unified rpicam-vid instance for both MJPEG streaming and IMX500 detection.
    Uses stdout for MJPEG, metadata file for detections.
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
        
        # MJPEG streaming state
        self._current_frame: Optional[bytes] = None
        self._frame_lock = threading.Lock()
        self._stream_thread: Optional[threading.Thread] = None
        
        print(f"[RPiCamStreaming] Initialized {width}x{height} @ {framerate}fps")
    
    def start(self):
        """Start rpicam-vid with MJPEG streaming and IMX500 detection."""
        if self._running:
            print("[RPiCamStreaming] Already running")
            return
        
        # Clean up old metadata
        if self.metadata_file.exists():
            self.metadata_file.unlink()
        
        # Build command: stream MJPEG to stdout, metadata to file
        cmd = [
            "rpicam-vid",
            "--post-process-file", "/usr/share/rpi-camera-assets/imx500_mobilenet_ssd.json",
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
        """Extract detections from metadata."""
        try:
            if "CnnOutputTensor" not in frame_data:
                return
            
            tensor = frame_data["CnnOutputTensor"]
            if not tensor or len(tensor) < 400:
                return
            
            # Extract class IDs from tensor
            class_ids = []
            for i in range(len(tensor) - 1, max(len(tensor) - 150, 0), -1):
                val = tensor[i]
                if val == 100.0:
                    break
                if 0 <= val < 90 and val == int(val):
                    class_ids.append(int(val))
            
            class_ids.reverse()
            
            if not class_ids:
                with self._detection_lock:
                    self._latest_detections = []
                return
            
            # Build detections
            detections = []
            for class_id in class_ids[:5]:
                if class_id < len(COCO_CLASSES):
                    class_name = COCO_CLASSES[class_id]
                    if class_name:
                        detections.append({
                            'class': class_name,
                            'class_id': class_id,
                            'confidence': 0.7,
                            'bbox': [0.0, 0.0, 0.0, 0.0]
                        })
            
            with self._detection_lock:
                self._latest_detections = detections
                    
        except Exception as e:
            pass
    
    def get_frame(self) -> Optional[bytes]:
        """Get latest JPEG frame."""
        with self._frame_lock:
            return self._current_frame
    
    def get_detections(self) -> List[Dict]:
        """Get latest detections."""
        with self._detection_lock:
            return self._latest_detections.copy()
    
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
