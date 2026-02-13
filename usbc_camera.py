# usbc_camera.py
from __future__ import annotations

from typing import Optional, Tuple
import cv2
import numpy as np
import time


class USBCCamera:
    """
    USB-C camera using OpenCV (cv2.VideoCapture) for webcam/USB camera access.
    Implements the same interface as BaslerCamera and MockCamera.
    """

    def __init__(self, device_index: int = 0):
        self.device_index = device_index
        self._cap: Optional[cv2.VideoCapture] = None

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

        # Flush buffer by reading a few frames to ensure we get a fresh capture
        # This prevents capturing frames from when the motor was still moving
        for _ in range(3):
            self._cap.read()
            time.sleep(0.05)  # Small delay between flushes
        
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

        return self._cap.read()

    def __enter__(self) -> "USBCCamera":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @staticmethod
    def list_available_cameras(max_index: int = 10) -> list[int]:
        """
        Test camera indices 0 through max_index-1 and return list of working indices.
        This can be slow as it attempts to open each camera briefly.
        """
        available = []
        for i in range(max_index):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                available.append(i)
                cap.release()
        return available
