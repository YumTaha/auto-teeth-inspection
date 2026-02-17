# usbc_camera.py
from __future__ import annotations

from typing import Optional, Tuple
import cv2
import numpy as np
import time
import threading
import platform

from pygrabber.dshow_graph import FilterGraph


class USBCCamera:
    """
    USB-C camera using OpenCV (cv2.VideoCapture) for webcam/USB camera access.
    Implements the same interface as BaslerCamera and MockCamera.
    
    Uses single high resolution (2560x1920) for both preview and capture to avoid
    Windows camera indicator flashing during resolution switching.
    """

    def __init__(self, device_index: Optional[int] = None, width: int = 2560, height: int = 1920):
        # Auto-detect Dino-Lite camera if no index provided
        if device_index is None:
            device_index = self.find_external_camera()
            if device_index is None:
                raise RuntimeError("No Dino-Lite camera detected. Please ensure it's connected.")
        
        self.device_index = device_index
        self._cap: Optional[cv2.VideoCapture] = None
        self._lock = threading.Lock()  # Prevent simultaneous access from preview and capture
        
        # Resolution settings
        self.width = width
        self.height = height

    @staticmethod
    def find_external_camera() -> Optional[int]:
        """
        Find Dino-Lite camera by device name using DirectShow enumeration.
        
        Returns the camera index if found, None otherwise.
        """
        try:
            devices = FilterGraph().get_input_devices()
            for index, name in enumerate(devices):
                # Match Dino-Lite camera by name (case-insensitive)
                if "dino-lite" in name.lower() or "dinolite" in name.lower():
                    print(f"[CAMERA] Detected Dino-Lite at index {index}: {name}")
                    return index
            
            print("[CAMERA] No Dino-Lite camera found in available devices:")
            for index, name in enumerate(devices):
                print(f"  [{index}] {name}")
        except Exception as e:
            print(f"[CAMERA] pygrabber detection failed: {e}")
        
        return None

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def open(self) -> None:
        if self.is_open:
            return

        # Use DirectShow backend on Windows for better camera control
        if platform.system() == 'Windows':
            self._cap = cv2.VideoCapture(self.device_index, cv2.CAP_DSHOW)
        else:
            self._cap = cv2.VideoCapture(self.device_index)
        
        if not self._cap.isOpened():
            self._cap = None
            raise RuntimeError(f"Failed to open camera at index {self.device_index}")
        
        # Set high resolution for both preview and capture
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

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
            # Flush buffer by reading frames to ensure we get a fresh capture
            # This prevents capturing stale frames from when motor was moving
            for _ in range(3):
                self._cap.read()
                time.sleep(0.03)
            
            # Capture the frame
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
                # Use DirectShow on Windows for detection
                if platform.system() == 'Windows':
                    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                else:
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
