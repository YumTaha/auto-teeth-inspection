# usbc_camera.py
from __future__ import annotations

from typing import Optional, Tuple
import cv2
import numpy as np
import time
import threading


class USBCCamera:
    """
    USB-C camera using OpenCV (cv2.VideoCapture) for webcam/USB camera access.
    Implements the same interface as BaslerCamera and MockCamera.
    """

    def __init__(self, device_index: int = 0):
        self.device_index = device_index
        self._cap: Optional[cv2.VideoCapture] = None
        self._lock = threading.Lock()  # Prevent simultaneous access from preview and capture

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def open(self) -> None:
        if self.is_open:
            return

        self._cap = cv2.VideoCapture(self.device_index)
        
        if not self._cap.isOpened():
            self._cap = None
            raise RuntimeError(f"Failed to open camera at index {self.device_index}")

    def close(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            finally:
                self._cap = None

    def capture_to(self, filepath: str, timeout_ms: int = 2000) -> None:
        if not self.is_open:
            raise RuntimeError("USB-C camera not open.")

        with self._lock:
            # Flush buffer by reading more frames to ensure we get a fresh capture
            # This prevents capturing frames from when the motor was still moving
            # or frames that are being read by the preview loop
            for _ in range(5):  # Increased from 3 to 5 for better buffer clearing
                self._cap.read()
                time.sleep(0.03)  # 30ms between flushes
            
            # Now capture the actual frame
            ret, frame = self._cap.read()
            if not ret or frame is None:
                raise RuntimeError("Failed to capture frame from USB-C camera.")

            # Save as PNG
            success = cv2.imwrite(filepath, frame)
            if not success:
                raise RuntimeError(f"Failed to save image to {filepath}")
            
            # Small delay to ensure file write is complete
            time.sleep(0.05)

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read a single frame for preview.
        Returns (success, frame) tuple where frame is BGR numpy array or None.
        """
        if not self.is_open:
            return False, None

        with self._lock:
            return self._cap.read()

    def __enter__(self) -> "USBCCamera":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @staticmethod
    def list_available_cameras(max_index: int = 5) -> list[int]:
        """
        Test camera indices 0 through max_index-1 and return list of working indices.
        Stops early after 2 consecutive failures to reduce noise.
        """
        # Suppress OpenCV warnings during detection (if supported)
        old_log_level = None
        try:
            if hasattr(cv2, 'getLogLevel'):
                old_log_level = cv2.getLogLevel()
                cv2.setLogLevel(cv2.LOG_LEVEL_ERROR)
        except:
            pass
        
        available = []
        consecutive_failures = 0
        
        try:
            for i in range(max_index):
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    available.append(i)
                    consecutive_failures = 0
                    cap.release()
                else:
                    consecutive_failures += 1
                    # Stop after 2 consecutive failures to avoid noise
                    if consecutive_failures >= 2:
                        break
        finally:
            # Restore log level if it was set
            if old_log_level is not None:
                try:
                    cv2.setLogLevel(old_log_level)
                except:
                    pass
        
        return available
