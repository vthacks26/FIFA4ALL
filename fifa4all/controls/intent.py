"""Map facial features to held-key intent.

Locked MVP mappings:
  head tilt / directional face movement → WASD (held while beyond dead zone)
  mouth open → Space (held while open)  — shot strength
  wink (exactly one eye closed) → L (held while winking)  — pass strength

Customizable gestures are out of scope for this MVP.
"""

from __future__ import annotations

from dataclasses import dataclass

from fifa4all.config import (
    KEY_BACK,
    KEY_FORWARD,
    KEY_LEFT,
    KEY_PASS,
    KEY_RIGHT,
    KEY_SHOOT,
    Config,
)
from fifa4all.vision.features import FaceFeatures


@dataclass(frozen=True)
class ControlIntent:
    hold_w: bool = False
    hold_a: bool = False
    hold_s: bool = False
    hold_d: bool = False
    hold_space: bool = False
    hold_l: bool = False

    def held_keys(self) -> frozenset[str]:
        keys: set[str] = set()
        if self.hold_w:
            keys.add(KEY_FORWARD)
        if self.hold_a:
            keys.add(KEY_LEFT)
        if self.hold_s:
            keys.add(KEY_BACK)
        if self.hold_d:
            keys.add(KEY_RIGHT)
        if self.hold_space:
            keys.add(KEY_SHOOT)
        if self.hold_l:
            keys.add(KEY_PASS)
        return frozenset(keys)

    def head_label(self) -> str:
        parts: list[str] = []
        if self.hold_w:
            parts.append("UP")
        if self.hold_s:
            parts.append("DOWN")
        if self.hold_a:
            parts.append("LEFT")
        if self.hold_d:
            parts.append("RIGHT")
        return "-".join(parts) if parts else "NEUTRAL"

    def keys_label(self) -> str:
        order = (KEY_FORWARD, KEY_LEFT, KEY_BACK, KEY_RIGHT, KEY_SHOOT, KEY_PASS)
        held = self.held_keys()
        shown = [k.upper() for k in order if k in held]
        return " ".join(shown) if shown else "(none)"


def _hysteresis(current: int, value: float, enter: float, exit_: float) -> int:
    if current == 0:
        if value >= enter:
            return 1
        if value <= -enter:
            return -1
        return 0
    if current == 1:
        return 1 if value >= exit_ else 0
    return -1 if value <= -exit_ else 0


class GestureEngine:
    """Stateful mapper: smoothing, dead zone, hysteresis, hold-while-active."""

    def __init__(self, config: Config | None = None) -> None:
        self.cfg = config or Config()
        self._yaw = 0.0
        self._pitch = 0.0
        self._has_smooth = False
        self._move_x = 0
        self._move_y = 0
        self._mouth = False
        self._wink = False
        self.neutral_yaw = 0.0
        self.neutral_pitch = 0.0
        self.neutral_mouth = 0.0
        self.calibrated = False
        self._calib: list[FaceFeatures] = []

    def reset(self) -> None:
        self._has_smooth = False
        self._move_x = 0
        self._move_y = 0
        self._mouth = False
        self._wink = False

    def add_calibration_sample(self, features: FaceFeatures) -> None:
        if features.detected:
            self._calib.append(features)

    def finish_calibration(self) -> None:
        if not self._calib:
            self.calibrated = True
            return
        n = float(len(self._calib))
        self.neutral_yaw = sum(f.yaw for f in self._calib) / n
        self.neutral_pitch = sum(f.pitch for f in self._calib) / n
        self.neutral_mouth = sum(f.mouth_open for f in self._calib) / n
        self.calibrated = True
        self._calib.clear()
        self.reset()

    def update(self, features: FaceFeatures) -> ControlIntent:
        if not features.detected:
            self.reset()
            return ControlIntent()

        if not self._has_smooth:
            self._yaw = features.yaw
            self._pitch = features.pitch
            self._has_smooth = True
        else:
            a = self.cfg.ema_alpha
            self._yaw = a * features.yaw + (1.0 - a) * self._yaw
            self._pitch = a * features.pitch + (1.0 - a) * self._pitch

        yaw = self._yaw - self.neutral_yaw
        pitch = self._pitch - self.neutral_pitch
        mouth = features.mouth_open - self.neutral_mouth

        self._move_x = _hysteresis(self._move_x, yaw, self.cfg.yaw_enter, self.cfg.yaw_exit)
        self._move_y = _hysteresis(
            self._move_y, pitch, self.cfg.pitch_enter, self.cfg.pitch_exit
        )

        if not self._mouth and mouth >= self.cfg.mouth_open:
            self._mouth = True
        elif self._mouth and mouth <= self.cfg.mouth_close:
            self._mouth = False

        left_closed = features.left_ear < self.cfg.wink_closed
        right_closed = features.right_ear < self.cfg.wink_closed
        left_open = features.left_ear > self.cfg.wink_open
        right_open = features.right_ear > self.cfg.wink_open
        one_wink = (left_closed and right_open) or (right_closed and left_open)
        both_open = left_open and right_open
        both_closed = left_closed and right_closed

        if not self._wink:
            self._wink = one_wink
        elif both_open or both_closed:
            # Blink (both closed) must not keep L held.
            self._wink = False

        return ControlIntent(
            hold_w=self._move_y > 0,
            hold_s=self._move_y < 0,
            hold_a=self._move_x < 0,
            hold_d=self._move_x > 0,
            hold_space=self._mouth,
            hold_l=self._wink,
        )

    @property
    def yaw_smoothed(self) -> float:
        return self._yaw - self.neutral_yaw

    @property
    def pitch_smoothed(self) -> float:
        return self._pitch - self.neutral_pitch
