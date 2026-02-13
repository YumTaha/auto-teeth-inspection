# runner.py
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from kinematics import index_to_angle_deg


@dataclass
class RunConfig:
    teeth: int
    captures: int
    outdir: str
    done_timeout_s: float = 15.0
    make_run_subfolder: bool = True


# optional callback signature for UI/logging
EventCb = Optional[Callable[[str], None]]


def run_inspection(
    cfg: RunConfig,
    motion,
    camera,
    stop_flag=None,
    on_event: EventCb = None,
) -> str:
    """
    Returns the folder where images were saved.
    motion must provide: hold(), move_abs(deg), wait_done(timeout_s, stop_flag=...)
    camera must provide: capture_to(filepath)
    """

    def emit(msg: str):
        if on_event:
            on_event(msg)

    if cfg.teeth <= 0:
        raise ValueError("cfg.teeth must be > 0")
    if cfg.captures <= 0:
        raise ValueError("cfg.captures must be > 0")

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
        emit(f"Move {i}/{cfg.captures - 1}: {target_deg:.6f} deg")

        motion.move_abs(target_deg)

        ok = motion.wait_done(cfg.done_timeout_s, stop_flag=stop_flag)
        if not ok:
            emit(f"WAIT DONE failed (timeout/stop) at index {i}.")
            break

        filename = f"tooth_{i:04d}_deg_{target_deg:.6f}.png"
        path = os.path.join(run_dir, filename)

        emit(f"Capturing image {i}...")
        camera.capture_to(path)
        emit(f"✓ Saved: {filename}")

    emit("Run complete.")
    return run_dir
