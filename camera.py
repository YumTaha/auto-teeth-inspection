# camera.py
from __future__ import annotations

from typing import Optional
from pypylon import pylon


class BaslerCamera:
    def __init__(self):
        self._cam: Optional[pylon.InstantCamera] = None

    @property
    def is_open(self) -> bool:
        return self._cam is not None and self._cam.IsOpen()

    def open(self) -> None:
        if self.is_open:
            return

        factory = pylon.TlFactory.GetInstance()
        devices = factory.EnumerateDevices()
        if not devices:
            raise RuntimeError("No Basler camera found.")

        self._cam = pylon.InstantCamera(factory.CreateDevice(devices[0]))
        self._cam.Open()

    def close(self) -> None:
        if self._cam is not None:
            try:
                if self._cam.IsGrabbing():
                    self._cam.StopGrabbing()
                if self._cam.IsOpen():
                    self._cam.Close()
            finally:
                self._cam = None

    def capture_to(self, filepath: str, timeout_ms: int = 2000) -> None:
        if not self.is_open:
            raise RuntimeError("Camera not open.")

        cam = self._cam
        cam.StartGrabbingMax(1)
        grab = cam.RetrieveResult(timeout_ms, pylon.TimeoutHandling_ThrowException)
        try:
            if not grab.GrabSucceeded():
                raise RuntimeError("Grab failed.")

            img = pylon.PylonImage()
            img.AttachGrabResultBuffer(grab)
            img.Save(pylon.ImageFileFormat_Png, filepath)
        finally:
            grab.Release()
            cam.StopGrabbing()

    def __enter__(self) -> "BaslerCamera":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
