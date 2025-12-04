"""
IMX500 Object Detection using rpicam-vid subprocess.
Runs periodic detection snapshots (1-2 seconds) to avoid camera lock conflict.
Main streaming uses Picamera2.
"""

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import List, Dict, Optional
import signal
import os

# COCO class names (matching MobileNet-SSD)
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


class RPiCamDetector:
    """
    Manages periodic rpicam-vid detection snapshots.
    Runs brief 2-second captures every 5 seconds to avoid camera lock.
    """
    
    def __init__(
        self,
        metadata_file: str = "/tmp/imx500_detections.json",
        confidence_threshold: float = 0.55,
        max_detections: int = 5,
        detection_interval: float = 5.0  # seconds between detection runs
    ):
        self.metadata_file = Path(metadata_file)
        self.confidence_threshold = confidence_threshold
        self.max_detections = max_detections
        self.detection_interval = detection_interval
        
        self._running = False
        self._latest_detections: List[Dict] = []
        self._detection_lock = threading.Lock()
        self._detection_thread: Optional[threading.Thread] = None
        
        print(f"[RPiCamDetector] Initialized (periodic mode)")
        print(f"[RPiCamDetector] Detection interval: {detection_interval}s")
        print(f"[RPiCamDetector] Confidence threshold: {self.confidence_threshold}")
    
    def start(self):
        """Start periodic detection thread."""
        if self._running:
            print("[RPiCamDetector] Already running")
            return
        
        self._running = True
        
        # Start detection thread
        self._detection_thread = threading.Thread(
            target=self._detection_loop,
            daemon=True,
            name="RPiCamDetector-Loop"
        )
        self._detection_thread.start()
        
        print(f"[RPiCamDetector] Started periodic detection (every {self.detection_interval}s)")
    
    def stop(self):
        """Stop detection thread."""
        if not self._running:
            return
        
        print("[RPiCamDetector] Stopping...")
        self._running = False
        
        # Wait for detection thread
        if self._detection_thread and self._detection_thread.is_alive():
            self._detection_thread.join(timeout=3)
        
        # Clean up metadata file
        if self.metadata_file.exists():
            self.metadata_file.unlink()
        
        print("[RPiCamDetector] Stopped")
    
    def _detection_loop(self):
        """Periodically run detection snapshots."""
        print("[RPiCamDetector] Detection loop started")
        
        # Wait for camera to initialize
        time.sleep(2)
        
        while self._running:
            try:
                # Run a 2-second detection snapshot
                self._run_detection_snapshot()
                
                # Wait before next detection
                time.sleep(self.detection_interval)
                
            except Exception as e:
                print(f"[RPiCamDetector] Detection loop error: {e}")
                time.sleep(5)
        
        print("[RPiCamDetector] Detection loop stopped")
    
    def _run_detection_snapshot(self):
        """Run a brief rpicam-vid capture for detection."""
        # Clean up old metadata file
        if self.metadata_file.exists():
            self.metadata_file.unlink()
        
        # Build rpicam-vid command (2 second capture)
        cmd = [
            "rpicam-vid",
            "--post-process-file", "/usr/share/rpi-camera-assets/imx500_mobilenet_ssd.json",
            "--width", "640",
            "--height", "480",
            "--framerate", "10",
            "--nopreview",
            "--metadata", str(self.metadata_file),
            "--metadata-format", "json",
            "-t", "2000",  # 2 seconds
            "-o", "/dev/null",  # Don't save video
        ]
        
        try:
            # Run subprocess and wait for completion
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=15,
                text=True
            )
            
            # Parse metadata file if it exists
            if self.metadata_file.exists():
                self._parse_metadata_file()
            
        except subprocess.TimeoutExpired:
            print("[RPiCamDetector] Detection snapshot timed out")
        except Exception as e:
            print(f"[RPiCamDetector] Detection snapshot error: {e}")
    
    def _parse_metadata_file(self):
        """Parse the complete metadata file."""
        try:
            with open(self.metadata_file, 'r') as f:
                content = f.read()
            
            if content.strip():
                self._parse_metadata_content(content)
                
        except Exception as e:
            print(f"[RPiCamDetector] Parse file error: {e}")
    
    def _parse_metadata_content(self, content: str):
        """Parse metadata JSON content and extract detections."""
        try:
            # The file contains a JSON array, we need to parse incrementally
            # Look for complete JSON objects
            if not content.strip():
                return
            
            # Simple approach: try to parse as complete JSON array
            # In production, use ijson for streaming parsing
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
            print(f"[RPiCamDetector] Parse error: {e}")
    
    def _extract_detections(self, frame_data: Dict):
        """Extract object detections from frame metadata."""
        try:
            # Check if this frame has detection output
            if "CnnOutputTensor" not in frame_data:
                return
            
            tensor = frame_data["CnnOutputTensor"]
            if not tensor or len(tensor) < 400:
                return
            
            # MobileNet-SSD output format (from IMX500):
            # The tensor contains detection results at the end
            # Class IDs are in the last ~100 elements
            # Format: [..., class_id, class_id, ..., 100.0] where 100.0 marks end
            
            # Extract class IDs from end of tensor (before the 100.0 marker)
            class_ids = []
            for i in range(len(tensor) - 1, max(len(tensor) - 150, 0), -1):
                val = tensor[i]
                if val == 100.0:
                    break
                if 0 <= val < 90 and val == int(val):  # Valid class ID
                    class_ids.append(int(val))
            
            # Reverse to get correct order
            class_ids.reverse()
            
            if not class_ids:
                with self._detection_lock:
                    self._latest_detections = []
                return
            
            # Build detection list
            detections = []
            for class_id in class_ids[:self.max_detections]:
                if class_id < len(COCO_CLASSES):
                    class_name = COCO_CLASSES[class_id]
                    if class_name:  # Skip empty class names
                        detections.append({
                            'class': class_name,
                            'class_id': class_id,
                            'confidence': 0.7,  # IMX500 already filtered by threshold
                            'bbox': [0.0, 0.0, 0.0, 0.0]  # Bounding boxes need more complex parsing
                        })
            
            # Update latest detections
            with self._detection_lock:
                self._latest_detections = detections
                
                # Log person detections
                person_count = sum(1 for d in detections if d['class'] == 'person')
                if person_count > 0:
                    print(f"[RPiCamDetector] Detected {person_count} person(s)")
                    
        except Exception as e:
            print(f"[RPiCamDetector] Detection extraction error: {e}")
    
    def get_detections(self) -> List[Dict]:
        """Get latest detections (thread-safe)."""
        with self._detection_lock:
            return self._latest_detections.copy()
    
    def is_running(self) -> bool:
        """Check if detector is running."""
        return self._running
    
    def get_person_count(self) -> int:
        """Get count of detected persons."""
        detections = self.get_detections()
        return sum(1 for d in detections if d['class'] == 'person')


# Global detector instance
_detector: Optional[RPiCamDetector] = None


def get_detector() -> RPiCamDetector:
    """Get or create global detector instance."""
    global _detector
    if _detector is None:
        _detector = RPiCamDetector()
    return _detector


def start_detector():
    """Start global detector."""
    detector = get_detector()
    if not detector.is_running():
        detector.start()


def stop_detector():
    """Stop global detector."""
    global _detector
    if _detector:
        _detector.stop()
        _detector = None
