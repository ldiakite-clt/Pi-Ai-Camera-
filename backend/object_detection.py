"""
Object detection using IMX500 AI accelerator with MobileNet-SSD (COCO dataset).
Detects 80 object classes including person, car, dog, etc.
"""

import time
import numpy as np
from typing import List, Dict, Optional
import json

# COCO dataset classes (80 classes)
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


class ObjectDetector:
    """Wrapper for IMX500 object detection"""
    
    def __init__(self, confidence_threshold=0.55):
        self.confidence_threshold = confidence_threshold
        self.last_detections = []
        self.person_detected_time = None
        
        # Model path - using MobileNet-SSD with post-processing
        self.model_path = "/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk"
        
        print(f"[ObjectDetector] Initializing with model: {self.model_path}")
        print(f"[ObjectDetector] Confidence threshold: {self.confidence_threshold}")
    
    def parse_detections(self, metadata: dict) -> List[Dict]:
        """
        Parse detection metadata from IMX500
        
        Returns list of detections with format:
        {
            'class': 'person',
            'class_id': 0,
            'confidence': 0.87,
            'bbox': [x, y, width, height],  # normalized 0-1
            'bbox_pixels': [x, y, width, height]  # pixel coordinates
        }
        """
        detections = []
        
        # IMX500 metadata is in the "imx500" key
        if "imx500" not in metadata:
            return detections
        
        imx500_meta = metadata["imx500"]
        
        # The detection results are in the output tensor
        # Format depends on the model, MobileNet-SSD outputs detections
        try:
            # Get detection results
            # Each detection is [class_id, confidence, x_min, y_min, x_max, y_max]
            if "results" in imx500_meta:
                results = imx500_meta["results"]
                
                for detection in results:
                    if len(detection) >= 6:
                        class_id = int(detection[0])
                        confidence = float(detection[1])
                        
                        # Skip low confidence detections
                        if confidence < self.confidence_threshold:
                            continue
                        
                        # Skip invalid class IDs
                        if class_id < 0 or class_id >= len(COCO_CLASSES):
                            continue
                        
                        class_name = COCO_CLASSES[class_id]
                        
                        # Skip empty class names
                        if not class_name:
                            continue
                        
                        # Bounding box (normalized coordinates 0-1)
                        x_min, y_min = float(detection[2]), float(detection[3])
                        x_max, y_max = float(detection[4]), float(detection[5])
                        
                        detections.append({
                            'class': class_name,
                            'class_id': class_id,
                            'confidence': confidence,
                            'bbox': [x_min, y_min, x_max - x_min, y_max - y_min],
                            'bbox_pixels': None  # Will be calculated by frontend
                        })
        
        except Exception as e:
            print(f"[ObjectDetector] Error parsing detections: {e}")
        
        self.last_detections = detections
        
        # Track person detection
        person_detected = any(d['class'] == 'person' for d in detections)
        if person_detected:
            self.person_detected_time = time.time()
        
        return detections
    
    def get_person_count(self) -> int:
        """Return number of people detected in last frame"""
        return sum(1 for d in self.last_detections if d['class'] == 'person')
    
    def is_person_detected(self) -> bool:
        """Check if person was detected recently (within last 2 seconds)"""
        if self.person_detected_time is None:
            return False
        return (time.time() - self.person_detected_time) < 2.0
