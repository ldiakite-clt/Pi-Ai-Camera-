"""
AI-enabled camera using IMX500 for object detection.
Separate from regular camera to allow IMX500-specific configuration.
"""

import io
import time
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from collections import deque

# Temporarily disable IMX500 - Picamera2 v0.3.30 has firmware upload race condition
# The IMX500 firmware upload internally starts camera before Picamera2.__init__ completes
# causing "AttributeError: 'Picamera2' object has no attribute 'allocator'"
# TODO: Find workaround or wait for Picamera2 fix
PICAMERA2_AVAILABLE = False
# try:
#     from picamera2 import Picamera2
#     from picamera2.devices.imx500 import IMX500, NetworkIntrinsics
#     PICAMERA2_AVAILABLE = True
# except Exception:
#     PICAMERA2_AVAILABLE = False

from PIL import Image, ImageDraw, ImageFont
import numpy as np

# COCO classes
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


class AICamera:
    """Camera with IMX500 AI object detection"""
    
    def __init__(self, size=(640, 480), confidence_threshold=0.55):
        self.size = size
        self.confidence_threshold = confidence_threshold
        self._pc2 = None
        self._imx500 = None
        self._started = False
        
        # Frame buffer for replays
        self._buffer = deque()
        self._buffer_max_seconds = 300
        
        # Model configuration
        self.model_path = "/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk"
        
        print(f"[AICamera] Initializing with IMX500 model: {self.model_path}")
        print(f"[AICamera] Confidence threshold: {self.confidence_threshold}")
        
        if PICAMERA2_AVAILABLE:
            try:
                # STEP 1: Initialize IMX500 FIRST (loads firmware safely)
                print("[AICamera] Loading IMX500 network firmware (this takes ~5 seconds)...")
                self._imx500 = IMX500(self.model_path)
                intrinsics = self._imx500.network_intrinsics
                intrinsics.task = "object detection"
                
                # STEP 2: Wait for firmware upload to complete
                print("[AICamera] Waiting for firmware upload to complete...")
                import time
                time.sleep(5)  # Give firmware upload time to finish
                
                # STEP 3: Create Picamera2 AFTER firmware is fully loaded
                print("[AICamera] Initializing Picamera2...")
                self._pc2 = Picamera2()
                
                # STEP 3: Configure camera - IMX500 is automatically integrated
                print("[AICamera] Configuring camera with IMX500...")
                config = self._pc2.create_preview_configuration(
                    main={"size": self.size},
                    buffer_count=6,
                    controls={"FrameRate": 30}
                )
                
                self._pc2.configure(config)
                
                # STEP 4: Start camera
                print("[AICamera] Starting camera with IMX500 AI processing...")
                self._pc2.start(show_preview=False)
                
                self._started = True
                print("[AICamera] Successfully initialized IMX500 with hardware acceleration!")
                
            except Exception as e:
                print(f"[AICamera] Failed to initialize IMX500: {e}")
                import traceback
                traceback.print_exc()
                self._pc2 = None
                self._imx500 = None
                self._started = False
    
    def get_frame_with_detections(self) -> Tuple[bytes, List[Dict]]:
        """
        Return JPEG frame and detected objects.
        
        Returns:
            (jpeg_bytes, detections_list)
            
        detections_list format:
        [
            {
                'class': 'person',
                'class_id': 0,
                'confidence': 0.87,
                'bbox': [x, y, w, h]  # normalized 0-1
            },
            ...
        ]
        """
        if not self._started or not self._pc2:
            jpeg = self._placeholder()
            self._push_buffer(jpeg)
            return jpeg, []
        
        try:
            # Capture frame as numpy array (CORRECT API for IMX500)
            array = self._pc2.capture_array("main")
            
            # Capture metadata separately (contains IMX500 detection results)
            metadata = self._pc2.capture_metadata()
            
            # Parse detections from IMX500 metadata
            detections = self._parse_detections(metadata)
            
            # Convert to JPEG
            img = Image.fromarray(array)
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            jpeg = buf.getvalue()
            
            # Push to buffer
            self._push_buffer(jpeg)
            
            return jpeg, detections
            
        except Exception as e:
            print(f"[AICamera] Error capturing frame: {e}")
            import traceback
            traceback.print_exc()
            jpeg = self._placeholder()
            self._push_buffer(jpeg)
            return jpeg, []
    
    def _parse_detections(self, metadata: dict) -> List[Dict]:
        """Parse IMX500 detection metadata using proper API"""
        detections = []
        
        if not metadata or not self._imx500:
            return detections
        
        try:
            # Get raw output tensors from IMX500
            outputs = self._imx500.get_outputs(metadata)
            
            if not outputs:
                return detections
            
            # MobileNet-SSD outputs: [boxes, scores, num_detections, classes]
            # boxes: shape (1, 10, 4) - [ymin, xmin, ymax, xmax]
            # scores: shape (1, 10)
            # num_detections: shape (1,)
            # classes: shape (1, 10)
            
            if len(outputs) < 4:
                return detections
            
            boxes = outputs[0][0]  # Remove batch dimension
            scores = outputs[1][0]
            num_detections = int(outputs[2][0])
            classes = outputs[3][0]
            
            # Process each detection
            for i in range(min(num_detections, len(boxes))):
                confidence = float(scores[i])
                
                # Filter by confidence
                if confidence < self.confidence_threshold:
                    continue
                
                class_id = int(classes[i])
                
                # Filter by valid class ID (COCO has 80 classes, 0-79)
                if class_id < 0 or class_id >= 80:
                    continue
                
                # Get class name from COCO dataset
                from object_detection import COCO_CLASSES
                class_name = COCO_CLASSES[class_id] if class_id < len(COCO_CLASSES) else f"class_{class_id}"
                
                # Bounding box (normalized 0-1): [ymin, xmin, ymax, xmax]
                ymin, xmin, ymax, xmax = boxes[i]
                
                # Convert to [x, y, w, h] format
                x = float(xmin)
                y = float(ymin)
                w = float(xmax - xmin)
                h = float(ymax - ymin)
                
                detections.append({
                    'class': class_name,
                    'class_id': class_id,
                    'confidence': round(confidence, 2),
                    'bbox': [x, y, w, h]
                })
        
        except Exception as e:
            print(f"[AICamera] Error parsing detections: {e}")
            import traceback
            traceback.print_exc()
        
        return detections
    
    def _push_buffer(self, jpeg: bytes) -> None:
        ts = int(time.time())
        self._buffer.append((ts, jpeg))
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
        text = f"AI Camera Unavailable\n{ts}"
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        d.multiline_text((10, 10), text, fill=(200, 200, 200), font=font)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    
    def is_available(self) -> bool:
        """Check if AI camera is working"""
        return self._started and self._pc2 is not None


# Singleton instance
_GLOBAL_AI_CAMERA: Optional[AICamera] = None


def get_global_ai_camera() -> AICamera:
    global _GLOBAL_AI_CAMERA
    if _GLOBAL_AI_CAMERA is None:
        _GLOBAL_AI_CAMERA = AICamera()
    return _GLOBAL_AI_CAMERA
