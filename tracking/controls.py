"""Canonical control state derivation shared by input output and the UI.

TECHNICAL_SPEC requires that the orientation visualization and the real input
logic use the same thresholds, so this module is the single source of truth for
the dead zone, the directional zones, and the expression edge triggers.

This module is pure geometry and state. It does not touch the camera, MediaPipe,
or the keyboard, so it stays importable and testable without webcam packages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, degrees, hypot
from typing import Literal, Mapping

Direction = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

# Screen-space note: the camera image is mirrored for the user, so a nose offset
# toward increasing image x means the user moved to their own left -> "A".
DIRECTION_KEYS: Mapping[Direction, tuple[str, ...]] = {
    "N": ("W",),
    "NE": ("W", "D"),
    "E": ("D",),
    "SE": ("S", "D"),
    "S": ("S",),
    "SW": ("S", "A"),
    "W": ("A",),
    "NW": ("W", "A"),
}

CARDINALS: tuple[Direction, ...] = ("N", "E", "S", "W")


@dataclass(frozen=True)
class ControlThresholds:
    """Thresholds for movement zones and expression triggers.

    The movement dead zone uses separate enter/exit radii. `exit_radius` must be
    larger than `enter_radius` so that a nose resting near the boundary does not
    chatter between moving and stopped.

    Expressions use a high trigger value and a lower reset value for the same
    reason, and are edge triggered so holding the expression emits one action.
    """

    enter_radius: float = 0.045
    exit_radius: float = 0.062
    y_scale: float = 1.15
    mouth_open: float = 0.090
    mouth_reset: float = 0.060
    wink_on: float = 0.025
    wink_off: float = 0.015
    dwell_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.enter_radius <= 0:
            raise ValueError("enter_radius must be positive")
        if self.exit_radius <= self.enter_radius:
            raise ValueError("exit_radius must be larger than enter_radius")
        if self.mouth_reset >= self.mouth_open:
            raise ValueError("mouth_reset must be below mouth_open")
        if self.wink_off >= self.wink_on:
            raise ValueError("wink_off must be below wink_on")
        if self.y_scale <= 0:
            raise ValueError("y_scale must be positive")

    def as_dict(self) -> dict[str, float]:
        """Publish thresholds to the UI so it can draw truthful zones."""

        return {
            "enter_radius": self.enter_radius,
            "exit_radius": self.exit_radius,
            "y_scale": self.y_scale,
            "mouth_open": self.mouth_open,
            "mouth_reset": self.mouth_reset,
            "wink_on": self.wink_on,
            "wink_off": self.wink_off,
            "dwell_seconds": self.dwell_seconds,
        }


def classify_direction(offset: tuple[float, float]) -> Direction:
    """Map a nose offset from center onto one of eight 45-degree zones.

    Image y grows downward, so a negative y offset means the user looked up.
    """

    dx, dy = offset
    # Zone boundaries sit halfway between axes, so shift by 22.5 degrees.
    angle = (degrees(atan2(-dy, dx)) + 22.5) % 360.0
    index = int(angle // 45.0)
    return ("E", "NE", "N", "NW", "W", "SW", "S", "SE")[index]


@dataclass
class _EdgeTrigger:
    """Rising-edge detector with a latch and a separate reset threshold."""

    on_value: float
    off_value: float
    latched: bool = False

    def update(self, value: float | None) -> tuple[bool, bool]:
        """Return (active, fired). `fired` is True only on the rising edge."""

        if value is None:
            self.latched = False
            return (False, False)
        if self.latched:
            if value <= self.off_value:
                self.latched = False
            return (self.latched, False)
        if value >= self.on_value:
            self.latched = True
            return (True, True)
        return (False, False)


@dataclass
class ControlStateMachine:
    """Turn smoothed face features into the UI/input control state contract."""

    thresholds: ControlThresholds = field(default_factory=ControlThresholds)
    center: tuple[float, float] | None = None
    _moving: bool = False
    _direction: Direction | None = None
    _mouth: _EdgeTrigger = field(init=False)
    _wink: _EdgeTrigger = field(init=False)

    def __post_init__(self) -> None:
        self._mouth = _EdgeTrigger(self.thresholds.mouth_open, self.thresholds.mouth_reset)
        self._wink = _EdgeTrigger(self.thresholds.wink_on, self.thresholds.wink_off)

    def calibrate(self, nose: tuple[float, float] | None) -> None:
        """Set the neutral center. Passing None clears calibration."""

        self.center = nose
        self._moving = False
        self._direction = None

    def update(
        self,
        *,
        nose: tuple[float, float] | None,
        features: Mapping[str, float],
        tracking_valid: bool,
    ) -> dict[str, object]:
        """Compute the control state for one frame.

        Losing tracking releases movement and clears expression latches so the
        game never keeps a key held down after the face disappears.
        """

        if not tracking_valid or nose is None:
            self._moving = False
            self._direction = None
            self._mouth.update(None)
            self._wink.update(None)
            return self._state(
                offset=(0.0, 0.0),
                mouth_value=None,
                wink_value=None,
                mouth_fired=False,
                wink_fired=False,
                tracking=False,
            )

        if self.center is None:
            self.center = nose

        offset = (nose[0] - self.center[0], nose[1] - self.center[1])
        self._update_movement(offset)

        mouth_value = features.get("mouth_opening")
        wink_value = features.get("left_wink")
        _, mouth_fired = self._mouth.update(mouth_value)
        _, wink_fired = self._wink.update(wink_value)

        return self._state(
            offset=offset,
            mouth_value=mouth_value,
            wink_value=wink_value,
            mouth_fired=mouth_fired,
            wink_fired=wink_fired,
            tracking=True,
        )

    def _update_movement(self, offset: tuple[float, float]) -> None:
        """Apply hysteresis so small motion near the boundary does not chatter."""

        radius = hypot(offset[0], offset[1] * self.thresholds.y_scale)
        boundary = self.thresholds.enter_radius if self._moving else self.thresholds.exit_radius
        if radius >= boundary:
            self._moving = True
            self._direction = classify_direction(offset)
        else:
            self._moving = False
            self._direction = None

    def _state(
        self,
        *,
        offset: tuple[float, float],
        mouth_value: float | None,
        wink_value: float | None,
        mouth_fired: bool,
        wink_fired: bool,
        tracking: bool,
    ) -> dict[str, object]:
        direction = self._direction
        keys = list(DIRECTION_KEYS[direction]) if direction is not None else []
        return {
            "centered": direction is None,
            "nose": {"x": round(offset[0], 4), "y": round(offset[1], 4)},
            "direction": direction,
            "keys": keys,
            "mouth": {
                "active": self._mouth.latched,
                "fired": mouth_fired,
                "value": mouth_value,
                "confidence": _confidence(mouth_value, self.thresholds.mouth_open),
            },
            "wink": {
                "active": self._wink.latched,
                "fired": wink_fired,
                "value": wink_value,
                "confidence": _confidence(wink_value, self.thresholds.wink_on),
            },
            "tracking": tracking,
        }


def _confidence(value: float | None, threshold: float) -> float:
    """Progress toward a trigger threshold, clamped to [0, 1], for UI meters."""

    if value is None or threshold <= 0:
        return 0.0
    return max(0.0, min(value / threshold, 1.0))
