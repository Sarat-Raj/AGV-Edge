"""
Warehouse AGV - OCR Aisle Sign Reader

Detects and reads aisle labels (e.g., H4, J12, A1) from camera frames
using EasyOCR. Designed to be called periodically, not every frame.
"""

import re
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np

try:
    import easyocr
except ImportError:
    print("[OCR] WARNING: easyocr not available - using mock mode")
    easyocr = None

import config


class AisleSign:
    """Detected aisle sign."""

    def __init__(self, label: str, confidence: float, bbox: List[List[int]], timestamp: float):
        self.label = label              # e.g., "H4"
        self.confidence = confidence    # 0-1
        self.bbox = bbox                # Bounding box corners
        self.timestamp = timestamp      # When detected

    def __repr__(self):
        return f"AisleSign('{self.label}', conf={self.confidence:.2f})"


class OCRReader:
    """
    Reads aisle signs from camera frames using EasyOCR.
    
    Optimized for Jetson Nano:
    - Only runs OCR periodically (not every frame)
    - Pre-processes image to focus on likely sign regions
    - Filters results to match aisle label patterns
    """

    def __init__(self):
        self.reader = None
        self.last_check_time = 0
        self.check_interval = config.OCR_CHECK_INTERVAL
        self.confidence_threshold = config.OCR_CONFIDENCE_THRESHOLD
        self.label_pattern = re.compile(config.AISLE_LABEL_PATTERN)

        # History of detected signs
        self.detected_signs: List[AisleSign] = []

        self._initialize()

    def _initialize(self):
        """Initialize EasyOCR reader."""
        if easyocr is None:
            print("[OCR] EasyOCR not available - mock mode")
            return

        try:
            # GPU=True for Jetson Nano CUDA
            self.reader = easyocr.Reader(
                ['en'],
                gpu=True,
                model_storage_directory='/tmp/easyocr_models'
            )
            print("[OCR] EasyOCR initialized (GPU mode)")
        except Exception as e:
            print(f"[OCR] GPU init failed, trying CPU: {e}")
            try:
                self.reader = easyocr.Reader(
                    ['en'],
                    gpu=False,
                    model_storage_directory='/tmp/easyocr_models'
                )
                print("[OCR] EasyOCR initialized (CPU mode)")
            except Exception as e2:
                print(f"[OCR] Failed to initialize: {e2}")

    def should_check(self) -> bool:
        """Check if enough time has passed since last OCR check."""
        return time.time() - self.last_check_time >= self.check_interval

    def preprocess(self, color_frame: np.ndarray) -> np.ndarray:
        """
        Preprocess frame to improve OCR accuracy on warehouse signs.
        
        Signs are typically:
        - High contrast (white/yellow text on dark background, or dark text on white)
        - Located at eye level or above (top half of frame)
        - Rectangular, with clear borders
        """
        # Focus on upper 2/3 of frame (signs are usually above ground level)
        h = color_frame.shape[0]
        upper_frame = color_frame[0:int(h * 0.7), :]

        # Convert to grayscale
        gray = cv2.cvtColor(upper_frame, cv2.COLOR_BGR2GRAY)

        # Enhance contrast (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Sharpen
        kernel = np.array([[-1, -1, -1],
                           [-1, 9, -1],
                           [-1, -1, -1]])
        sharpened = cv2.filter2D(enhanced, -1, kernel)

        return sharpened

    def read_signs(self, color_frame: np.ndarray) -> List[AisleSign]:
        """
        Attempt to read aisle signs from the current frame.
        
        Args:
            color_frame: BGR image from camera
            
        Returns:
            List of detected AisleSign objects matching aisle label patterns
        """
        if self.reader is None:
            return []

        if not self.should_check():
            return []

        self.last_check_time = time.time()

        # Preprocess
        processed = self.preprocess(color_frame)

        # Run OCR
        try:
            results = self.reader.readtext(
                processed,
                detail=1,
                paragraph=False,
                min_size=20,
                text_threshold=0.6,
                low_text=0.3,
            )
        except Exception as e:
            print(f"[OCR] Error: {e}")
            return []

        # Filter for aisle labels
        signs = []
        for (bbox, text, confidence) in results:
            # Clean up text
            text_clean = text.strip().upper().replace(" ", "").replace(".", "")

            # Check if it matches aisle label pattern
            if self.label_pattern.match(text_clean) and confidence >= self.confidence_threshold:
                sign = AisleSign(
                    label=text_clean,
                    confidence=confidence,
                    bbox=bbox,
                    timestamp=time.time()
                )
                signs.append(sign)
                print(f"[OCR] Detected: {sign}")

        # Add to history
        self.detected_signs.extend(signs)

        return signs

    def get_latest_sign(self) -> Optional[AisleSign]:
        """Get the most recently detected sign."""
        if not self.detected_signs:
            return None
        return self.detected_signs[-1]

    def get_unique_labels(self) -> List[str]:
        """Get all unique aisle labels detected so far."""
        seen = set()
        unique = []
        for sign in self.detected_signs:
            if sign.label not in seen:
                seen.add(sign.label)
                unique.append(sign.label)
        return unique

    def estimate_sign_distance(self, depth_meters: np.ndarray, bbox: List[List[int]]) -> Optional[float]:
        """
        Estimate the distance to a detected sign using depth data.
        
        Args:
            depth_meters: Depth image in meters
            bbox: Bounding box of the detected text
            
        Returns:
            Distance in meters, or None if depth unavailable
        """
        # Get center of bounding box
        pts = np.array(bbox)
        cx = int(np.mean(pts[:, 0]))
        cy = int(np.mean(pts[:, 1]))

        # Sample depth around center
        region_size = 5
        y_start = max(0, cy - region_size)
        y_end = min(depth_meters.shape[0], cy + region_size)
        x_start = max(0, cx - region_size)
        x_end = min(depth_meters.shape[1], cx + region_size)

        region = depth_meters[y_start:y_end, x_start:x_end]
        valid = region[(region > 0.1) & (region < config.OCTOMAP_MAX_RANGE)]

        if len(valid) > 0:
            return float(np.median(valid))
        return None


# --- Quick test ---
if __name__ == "__main__":
    reader = OCRReader()

    # Create a test image with text
    test_img = np.ones((240, 320, 3), dtype=np.uint8) * 200
    cv2.putText(test_img, "H4", (130, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)

    print("Testing OCR on synthetic image...")
    signs = reader.read_signs(test_img)
    if signs:
        for s in signs:
            print(f"  Found: {s}")
    else:
        print("  No signs detected (may need real signage)")

    print(f"\nUnique labels: {reader.get_unique_labels()}")
