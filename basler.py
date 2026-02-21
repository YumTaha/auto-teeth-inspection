# basler.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple
import threading
import os

import numpy as np
import cv2

from pypylon import pylon


@dataclass
class BaslerConfig:
    # If multiple cameras connected, set this to pick a specific device
    serial_number: Optional[str] = None

    # Optional camera tuning (best-effort; depends on camera model)
    exposure_us: Optional[float] = None
    gain: Optional[float] = None
    fps: Optional[float] = None  # may require enabling AcquisitionFrameRateEnable

    # Grab timeout
    timeout_ms: int = 1000


class BaslerCamera:
    """
    Minimal camera interface used by the project:
      - open()
      - close()
      - is_open (property)
      - read_frame() -> (ok, frame_bgr)
      - capture_to(path)
    """

    def __init__(self, cfg: Optional[BaslerConfig] = None):
        self.cfg = cfg or BaslerConfig()
        self._lock = threading.Lock()

        self._camera: Optional[pylon.InstantCamera] = None
        self._converter: Optional[pylon.ImageFormatConverter] = None

    @property
    def is_open(self) -> bool:
        return self._camera is not None and self._camera.IsOpen()

    def open(self) -> None:
        with self._lock:
            if self.is_open:
                return

            tl_factory = pylon.TlFactory.GetInstance()
            devices = tl_factory.EnumerateDevices()
            if not devices:
                raise RuntimeError("No Basler camera found (EnumerateDevices returned empty).")

            # Pick device (by serial if provided, otherwise first camera)
            device_info = None
            if self.cfg.serial_number:
                for d in devices:
                    try:
                        if d.GetSerialNumber() == self.cfg.serial_number:
                            device_info = d
                            break
                    except Exception:
                        continue
                if device_info is None:
                    raise RuntimeError(f"Basler camera with serial '{self.cfg.serial_number}' not found.")
            else:
                device_info = devices[0]

            device = tl_factory.CreateDevice(device_info)
            cam = pylon.InstantCamera(device)
            cam.Open()

            # Prepare converter to get BGR for OpenCV/Tkinter
            conv = pylon.ImageFormatConverter()
            conv.OutputPixelFormat = pylon.PixelType_BGR8packed
            conv.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

            self._apply_optional_settings(cam)

            # For preview: latest image only keeps latency low
            cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

            self._camera = cam
            self._converter = conv

    def close(self) -> None:
        with self._lock:
            if self._camera is None:
                return

            try:
                if self._camera.IsGrabbing():
                    self._camera.StopGrabbing()
            except Exception:
                pass

            try:
                if self._camera.IsOpen():
                    self._camera.Close()
            except Exception:
                pass

            self._camera = None
            self._converter = None

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Return a single frame for preview.
        Returns (ok, frame_bgr).
        """
        with self._lock:
            if not self.is_open or self._camera is None or self._converter is None:
                return False, None

            # Make sure we are grabbing
            if not self._camera.IsGrabbing():
                try:
                    self._camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
                except Exception:
                    return False, None

            try:
                grab = self._camera.RetrieveResult(
                    int(self.cfg.timeout_ms),
                    pylon.TimeoutHandling_Return,  # no exception on timeout
                )
                if grab is None:
                    return False, None

                try:
                    if not grab.GrabSucceeded():
                        return False, None

                    frame_bgr = self._grab_to_bgr(grab)
                    return True, frame_bgr
                finally:
                    grab.Release()

            except Exception:
                return False, None

    def capture_to(self, filepath: str) -> None:
        """
        Grab one frame and save it to disk (PNG/JPG based on extension).
        This saves the raw captured frame (no overlays).
        """
        folder = os.path.dirname(filepath)
        if folder:
            os.makedirs(folder, exist_ok=True)

        with self._lock:
            if not self.is_open or self._camera is None or self._converter is None:
                raise RuntimeError("Basler camera is not open.")

            grab = self._camera.RetrieveResult(
                int(self.cfg.timeout_ms),
                pylon.TimeoutHandling_ThrowException,
            )
            try:
                if not grab.GrabSucceeded():
                    raise RuntimeError("Basler grab failed (GrabSucceeded == False).")

                frame_bgr = self._grab_to_bgr(grab)

                ok = cv2.imwrite(filepath, frame_bgr)
                if not ok:
                    raise RuntimeError(f"Failed to save image to: {filepath}")

            finally:
                try:
                    grab.Release()
                except Exception:
                    pass

    # -------------------------
    # Internals
    # -------------------------
    def _grab_to_bgr(self, grab_result) -> np.ndarray:
        # Convert to BGR8packed numpy array
        converted = self._converter.Convert(grab_result)
        arr = converted.GetArray()  # numpy array

        # Ensure BGR shape (H, W, 3)
        if arr.ndim == 2:
            # Mono -> BGR
            return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
        if arr.ndim == 3 and arr.shape[2] == 3:
            return arr

        raise RuntimeError(f"Unexpected image shape from Basler: {arr.shape}")

    def _apply_optional_settings(self, cam: pylon.InstantCamera) -> None:
        # Exposure (node names vary; best-effort)
        if self.cfg.exposure_us is not None:
            for node_name in ("ExposureTime", "ExposureTimeAbs"):
                try:
                    node = getattr(cam, node_name)
                    node.Value = float(self.cfg.exposure_us)
                    break
                except Exception:
                    continue

        # Gain
        if self.cfg.gain is not None:
            try:
                cam.Gain.Value = float(self.cfg.gain)
            except Exception:
                pass

        # FPS (may need enabling)
        if self.cfg.fps is not None:
            try:
                if hasattr(cam, "AcquisitionFrameRateEnable"):
                    try:
                        cam.AcquisitionFrameRateEnable.Value = True
                    except Exception:
                        pass
                if hasattr(cam, "AcquisitionFrameRate"):
                    cam.AcquisitionFrameRate.Value = float(self.cfg.fps)
            except Exception:
                pass
