# runner.py
"""
Pure inspection execution engine.

Coordinates motor movements and camera captures without any API knowledge.
Fully modular - can be used for local-only inspections, different APIs, or testing.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from kinematics import index_to_angle_deg


@dataclass
class RunConfig:
    """Configuration for inspection run (core parameters only)."""
    teeth: int
    captures: int
    outdir: str
    done_timeout_s: float = 15.0
    make_run_subfolder: bool = True


# Callback type signatures
EventCb = Optional[Callable[[str], None]]
ImageCb = Optional[Callable[[str], None]]
FileCb = Optional[Callable[[str, int], None]]  # (filepath, tooth_number)


def run_inspection(
    cfg: RunConfig,
    motion,
    camera,
    stop_flag=None,
    on_event: EventCb = None,
    on_image_captured: ImageCb = None,
    on_file_ready: FileCb = None,
) -> str:
    """
    Execute inspection loop: motor movements + camera captures.
    
    This is a pure inspection engine with no API knowledge. It coordinates
    hardware and emits callbacks when files are ready - the caller decides
    what to do with them (upload, copy, compress, etc.).
    
    Args:
        cfg: Inspection configuration (teeth count, output dir, etc.)
        motion: Motion controller with methods: hold(), move_abs(deg), wait_done(timeout, stop_flag)
        camera: Camera with method: capture_to(filepath)
        stop_flag: Optional threading.Event for stopping inspection
        on_event: Optional callback for logging/status messages
        on_image_captured: Optional callback for preview display (called with filepath)
        on_file_ready: Optional callback when file is saved (filepath, tooth_number)
                       Caller handles upload/cleanup/etc.
    
    Returns:
        Path to directory containing captured images
    """

    def emit(msg: str):
        """Helper to emit event messages."""
        if on_event:
            on_event(msg)

    # Validate configuration
    if cfg.teeth <= 0:
        raise ValueError("cfg.teeth must be > 0")
    if cfg.captures <= 0:
        raise ValueError("cfg.captures must be > 0")

    # Create output directory
    base = cfg.outdir
    os.makedirs(base, exist_ok=True)

    if cfg.make_run_subfolder:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = os.path.join(base, f"run_{stamp}")
    else:
        run_dir = base

    os.makedirs(run_dir, exist_ok=True)
    emit(f"Run dir: {run_dir}")

    # Ensure motor is holding before we start
    motion.hold()

    # Main inspection loop
    for i in range(cfg.captures):
        # Check for stop signal
        if stop_flag is not None and stop_flag.is_set():
            emit("Stopped.")
            break

        # Calculate target angle for this tooth
        target_deg = index_to_angle_deg(i, cfg.teeth)
        emit(f"Move {i+1}/{cfg.captures}: {target_deg:.6f} deg")

        # Move motor to position
        motion.move_abs(target_deg)

        # Wait for movement to complete
        ok = motion.wait_done(cfg.done_timeout_s, stop_flag=stop_flag)
        if not ok:
            emit(f"WAIT DONE failed (timeout/stop) at move {i+1}.")
            break

        # Capture image
        tooth_num = i + 1  # Tooth numbering starts at 1
        filename = f"tooth_{tooth_num:04d}_deg_{target_deg:.6f}.png"
        path = os.path.join(run_dir, filename)

        emit(f"Capturing image {i+1}...")
        camera.capture_to(path)
        emit(f"✓ Saved: {filename}")
        
        # Notify caller that file is ready (for upload, backup, etc.)
        if on_file_ready:
            on_file_ready(path, tooth_num)
        
        # Show captured image in preview
        if on_image_captured:
            on_image_captured(path)

    emit("Run complete.")
    
    return run_dir
