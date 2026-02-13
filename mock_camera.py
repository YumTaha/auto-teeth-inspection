# mock_camera.py
from __future__ import annotations

import time
from typing import Optional


class MockCamera:
    """
    Mock camera that simulates BaslerCamera interface for testing
    without actual hardware. Just prints messages instead of saving images.
    """

    def __init__(self):
        self._is_open_flag: bool = False

    @property
    def is_open(self) -> bool:
        return self._is_open_flag

    def open(self) -> None:
        if self.is_open:
            return
        print("📷 Mock camera opened")
        self._is_open_flag = True

    def close(self) -> None:
        if not self._is_open_flag:
            return
        print("📷 Mock camera closed")
        self._is_open_flag = False

    def capture_to(self, filepath: str, timeout_ms: int = 2000) -> None:
        if not self.is_open:
            raise RuntimeError("Mock camera not open.")

        time.sleep(0.2)
        
        print(f"📷 Mock picture taken, saved to: {filepath}")

    def __enter__(self) -> "MockCamera":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
