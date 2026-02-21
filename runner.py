# runner.py
from __future__ import annotations

import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from kinematics import index_to_angle_deg
from api_client import ApiClient


@dataclass
class RunConfig:
    teeth: int
    captures: int
    outdir: str
    done_timeout_s: float = 15.0
    make_run_subfolder: bool = True
    observation_id: Optional[int] = None
    api_config: Optional[Any] = None
    cleanup_temp_files: bool = False  # Delete files after successful upload


# optional callback signature for UI/logging
EventCb = Optional[Callable[[str], None]]
ImageCb = Optional[Callable[[str], None]]  # Callback for displaying captured images
UploadCb = Optional[Callable[[int, bool, Optional[str]], None]]  # (tooth_number, ok, err)


def run_inspection(
    cfg: RunConfig,
    motion,
    camera,
    stop_flag=None,
    on_event: EventCb = None,
    on_image_captured: ImageCb = None,
    on_upload_result: UploadCb = None,
) -> str:
    """
    Returns the folder where images were saved.
    motion must provide: hold(), move_abs(deg), wait_done(timeout_s, stop_flag=...)
    camera must provide: capture_to(filepath)
    on_image_captured: optional callback called with filepath after each capture
    """

    def emit(msg: str):
        if on_event:
            on_event(msg)

    if cfg.teeth <= 0:
        raise ValueError("cfg.teeth must be > 0")
    if cfg.captures <= 0:
        raise ValueError("cfg.captures must be > 0")

    # Use temp directory if cleanup is enabled, otherwise use configured outdir
    if cfg.cleanup_temp_files:
        run_dir = tempfile.mkdtemp(prefix="inspection_")
        emit(f"Using temp dir: {run_dir}")
    else:
        base = cfg.outdir
        os.makedirs(base, exist_ok=True)

        if cfg.make_run_subfolder:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = os.path.join(base, f"run_{stamp}")
        else:
            run_dir = base

        os.makedirs(run_dir, exist_ok=True)
        emit(f"Run dir: {run_dir}")

    # Make sure motor is holding before start
    motion.hold()

    for i in range(cfg.captures):
        if stop_flag is not None and stop_flag.is_set():
            emit("Stopped.")
            break

        target_deg = index_to_angle_deg(i, cfg.teeth)
        emit(f"Move {i+1}/{cfg.captures}: {target_deg:.6f} deg")

        motion.move_abs(target_deg)

        ok = motion.wait_done(cfg.done_timeout_s, stop_flag=stop_flag)
        if not ok:
            emit(f"WAIT DONE failed (timeout/stop) at move {i+1}.")
            break

        tooth_num = i + 1  # Tooth numbering starts at 1
        filename = f"tooth_{tooth_num:04d}_deg_{target_deg:.6f}.png"
        path = os.path.join(run_dir, filename)

        emit(f"Capturing image {i+1}...")
        camera.capture_to(path)
        emit(f"✓ Saved: {filename}")
        
        # Upload to observation if configured (non-blocking)
        if cfg.observation_id is not None and cfg.api_config is not None:
            def upload_worker(obs_id, api_cfg, file_path, tooth_number, cleanup):
                """Background worker to upload image without blocking."""
                try:
                    client = ApiClient(api_cfg)
                    client.upload_attachment(obs_id, file_path, tag=tooth_number)
                    emit(f"✓ Uploaded tooth_{tooth_number} to observation")
                    if on_upload_result:
                        on_upload_result(tooth_number, True, None)
                    
                    # Delete file after successful upload if cleanup is enabled
                    if cleanup:
                        try:
                            os.remove(file_path)
                            emit(f"✓ Deleted temp file: tooth_{tooth_number}")
                        except Exception as del_err:
                            emit(f"⚠ Failed to delete temp file tooth_{tooth_number}: {del_err}")
                except Exception as e:
                    emit(f"⚠ Upload failed for tooth_{tooth_number}: {e}")
                    if on_upload_result:
                        on_upload_result(tooth_number, False, str(e))

            # Start upload in background thread
            upload_thread = threading.Thread(
                target=upload_worker,
                args=(cfg.observation_id, cfg.api_config, path, tooth_num, cfg.cleanup_temp_files),
                daemon=True
            )
            upload_thread.start()
        
        # Show the captured image in preview
        if on_image_captured:
            on_image_captured(path)

    emit("Run complete.")
    
    # Note: Individual temp files are deleted after successful upload
    # The temp directory itself is left for the OS to clean up
    
    return run_dir
