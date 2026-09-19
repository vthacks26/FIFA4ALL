"""Head-pose extraction and smoothing.

Converts MediaPipe's 4x4 facial transformation matrix into intuitive yaw / pitch
/ roll angles, and provides an exponential-moving-average smoother to remove the
landmark jitter described in joe_plan.txt section 13.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class HeadPose:
    """Head orientation in degrees.

    Convention used throughout the control layer:
      * yaw:   positive = head turned to the player's right
      * pitch: positive = head tilted down (chin toward chest)
      * roll:  positive = head tilted so right ear approaches shoulder
    """

    yaw: float
    pitch: float
    roll: float


def head_pose_from_matrix(matrix: np.ndarray) -> HeadPose:
    """Extract yaw/pitch/roll (degrees) from a 4x4 transformation matrix."""

    rotation = np.asarray(matrix)[:3, :3]
    sy = math.sqrt(rotation[0, 0] ** 2 + rotation[1, 0] ** 2)
    yaw = math.degrees(math.atan2(-rotation[2, 0], sy))
    pitch = math.degrees(math.atan2(rotation[2, 1], rotation[2, 2]))
    roll = math.degrees(math.atan2(rotation[1, 0], rotation[0, 0]))
    return HeadPose(yaw=yaw, pitch=pitch, roll=roll)


class PoseSmoother:
    """Exponential moving average low-pass filter for head pose.

    ``alpha`` is the weight of the newest sample (0 < alpha <= 1). Smaller values
    are smoother but less responsive.
    """

    def __init__(self, alpha: float = 0.4):
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be in (0, 1]")
        self.alpha = alpha
        self._state: Optional[HeadPose] = None

    def reset(self) -> None:
        self._state = None

    def update(self, pose: HeadPose) -> HeadPose:
        if self._state is None:
            self._state = pose
            return pose
        a = self.alpha
        self._state = HeadPose(
            yaw=a * pose.yaw + (1 - a) * self._state.yaw,
            pitch=a * pose.pitch + (1 - a) * self._state.pitch,
            roll=a * pose.roll + (1 - a) * self._state.roll,
        )
        return self._state
