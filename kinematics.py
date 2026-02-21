# kinematics.py
from __future__ import annotations

def _step_angle_deg(teeth: int) -> float:
    if teeth <= 0:
        raise ValueError("teeth must be > 0")
    return 360.0 / float(teeth)

def index_to_angle_deg(index: int, teeth: int) -> float:
    # absolute angle for tooth index (0..)
    return float(index) * _step_angle_deg(teeth)
