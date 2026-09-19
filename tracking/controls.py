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
from time import monotonic
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
    # Degrees a held direction keeps past its 45-degree zone before handing
    # over. Without this the nose resting on a boundary flaps between, say, N
    # and NE, which stutters movement in game.
    angle_margin: float = 9.0
    # Posture settles over a few minutes, the calibrated centre moves with it,
    # and the player walks with no input. If the nose holds still outside the
    # dead zone for this long it is drift, not intent, so re-centre there.
    # Deliberately longer than a steering input is ever held dead still.
    recentre_seconds: float = 3.5
    # How far the nose may wander and still count as held still.
    recentre_stillness: float = 0.012
    mouth_open: float = 0.090
    mouth_reset: float = 0.060
    # A resting mouth does not read zero, and how high it reads varies by face.
    # Measured at 0.064 on one tester, above the 0.060 release threshold, which
    # latches Space open forever once triggered. Calibration samples the resting
    # value and lifts the release just above it. These only ever raise the
    # thresholds, so a face that rests low keeps the team's tuned values.
    mouth_rest_clearance: float = 0.008
    mouth_min_gap: float = 0.030
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
        if self.mouth_rest_clearance <= 0:
            raise ValueError("mouth_rest_clearance must be positive")
        if self.mouth_min_gap <= 0:
            raise ValueError("mouth_min_gap must be positive")
        if self.wink_off >= self.wink_on:
            raise ValueError("wink_off must be below wink_on")
        if self.y_scale <= 0:
            raise ValueError("y_scale must be positive")
        if not 0.0 <= self.angle_margin < 22.5:
            raise ValueError("angle_margin must be within half a zone")
        if self.recentre_seconds <= 0:
            raise ValueError("recentre_seconds must be positive")
        if self.recentre_stillness <= 0:
            raise ValueError("recentre_stillness must be positive")

    def as_dict(self) -> dict[str, float]:
        """Publish thresholds to the UI so it can draw truthful zones."""

        return {
            "enter_radius": self.enter_radius,
            "exit_radius": self.exit_radius,
            "y_scale": self.y_scale,
            "angle_margin": self.angle_margin,
            "recentre_seconds": self.recentre_seconds,
            "recentre_stillness": self.recentre_stillness,
            "mouth_open": self.mouth_open,
            "mouth_reset": self.mouth_reset,
            "mouth_rest_clearance": self.mouth_rest_clearance,
            "mouth_min_gap": self.mouth_min_gap,
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
    """Rising-edge detector with a latch and a separate reset threshold.

    Also tracks how long the latch has been engaged, which is what shot power
    is derived from. Measuring it here rather than in the output layer means
    the UI shows a truthful gesture duration whether or not input is armed.
    """

    on_value: float
    off_value: float
    latched: bool = False
    _since: float | None = None

    def update(self, value: float | None, now: float) -> tuple[bool, bool]:
        """Return (active, fired). `fired` is True only on the rising edge."""

        if value is None:
            self.latched = False
            self._since = None
            return (False, False)
        if self.latched:
            if value <= self.off_value:
                self.latched = False
                self._since = None
            return (self.latched, False)
        if value >= self.on_value:
            self.latched = True
            self._since = now
            return (True, True)
        return (False, False)

    def held_seconds(self, now: float) -> float:
        return 0.0 if self._since is None else max(now - self._since, 0.0)


@dataclass
class ControlStateMachine:
    """Turn smoothed face features into the UI/input control state contract."""

    thresholds: ControlThresholds = field(default_factory=ControlThresholds)
    center: tuple[float, float] | None = None
    mouth_rest: float | None = None
    auto_recentre: bool = True
    recentred: bool = False
    _moving: bool = False
    _direction: Direction | None = None
    _still_since: float | None = None
    _still_anchor: tuple[float, float] | None = None
    _wink_eye: str | None = None
    _mouth: _EdgeTrigger = field(init=False)
    _wink: _EdgeTrigger = field(init=False)

    def __post_init__(self) -> None:
        self._mouth = _EdgeTrigger(self.thresholds.mouth_open, self.thresholds.mouth_reset)
        self._wink = _EdgeTrigger(self.thresholds.wink_on, self.thresholds.wink_off)

    def calibrate(
        self, nose: tuple[float, float] | None, *, mouth_rest: float | None = None
    ) -> None:
        """Set the neutral centre, and optionally the resting mouth baseline.

        `mouth_rest` is the mouth-opening ratio measured while the user sits
        neutral. It raises the release threshold clear of that value so the
        shoot latch cannot stick open.
        """

        self.center = nose
        if mouth_rest is not None:
            self.mouth_rest = mouth_rest
            self._apply_mouth_thresholds()
        self._moving = False
        self._direction = None
        self._still_since = None
        self._still_anchor = None

    def update(
        self,
        *,
        nose: tuple[float, float] | None,
        features: Mapping[str, float],
        tracking_valid: bool,
        now: float | None = None,
    ) -> dict[str, object]:
        """Compute the control state for one frame.

        Losing tracking releases movement and clears expression latches so the
        game never keeps a key held down after the face disappears.
        """

        moment = monotonic() if now is None else now
        self.recentred = False

        if not tracking_valid or nose is None:
            self._moving = False
            self._direction = None
            self._still_since = None
            self._still_anchor = None
            self._wink_eye = None
            self._mouth.update(None, moment)
            self._wink.update(None, moment)
            return self._state(
                offset=(0.0, 0.0),
                nose_point=None,
                mouth_value=None,
                wink_value=None,
                mouth_fired=False,
                wink_fired=False,
                tracking=False,
                now=moment,
            )

        if self.center is None:
            self.center = nose

        offset = (nose[0] - self.center[0], nose[1] - self.center[1])
        self._update_movement(offset)
        if self.auto_recentre and self._drifted(nose, moment):
            self.center = nose
            self.recentred = True
            self._still_since = None
            self._still_anchor = None
            offset = (0.0, 0.0)
            self._update_movement(offset)

        mouth_value = features.get("mouth_opening")
        # `left_wink` is signed: positive when the left eye is more closed,
        # negative when the right eye is. Magnitude is what matters, so either
        # eye triggers a pass. Blinking both eyes moves them together and
        # leaves the difference near zero, so it still does not fire.
        signed_wink = features.get("left_wink")
        wink_value = None if signed_wink is None else abs(signed_wink)
        self._wink_eye = _wink_eye(signed_wink, self.thresholds.wink_off)
        _, mouth_fired = self._mouth.update(mouth_value, moment)
        _, wink_fired = self._wink.update(wink_value, moment)

        return self._state(
            offset=offset,
            nose_point=nose,
            mouth_value=mouth_value,
            wink_value=wink_value,
            mouth_fired=mouth_fired,
            wink_fired=wink_fired,
            tracking=True,
            now=moment,
        )

    def _update_movement(self, offset: tuple[float, float]) -> None:
        """Apply hysteresis so small motion near the boundary does not chatter."""

        radius = hypot(offset[0], offset[1] * self.thresholds.y_scale)
        boundary = self.thresholds.enter_radius if self._moving else self.thresholds.exit_radius
        if radius < boundary:
            self._moving = False
            self._direction = None
            return

        candidate = classify_direction(offset)
        if self._direction is not None and candidate != self._direction:
            # Hold the current zone until the nose clears its widened boundary.
            if _within_zone(offset, self._direction, self.thresholds.angle_margin):
                candidate = self._direction
        self._moving = True
        self._direction = candidate

    def _apply_mouth_thresholds(self) -> None:
        """Lift the mouth thresholds clear of this person's resting value."""

        rest = self.mouth_rest
        if rest is None:
            return
        reset = max(self.thresholds.mouth_reset, rest + self.thresholds.mouth_rest_clearance)
        self._mouth.off_value = reset
        self._mouth.on_value = max(self.thresholds.mouth_open, reset + self.thresholds.mouth_min_gap)

    @property
    def mouth_thresholds(self) -> tuple[float, float]:
        """Effective (open, reset) after any resting-mouth calibration."""

        return (self._mouth.on_value, self._mouth.off_value)

    def _drifted(self, nose: tuple[float, float], now: float) -> bool:
        """True when the nose has been held still outside the dead zone.

        Holding still while the system reports movement can only mean the
        neutral centre has drifted away from where the user actually rests.
        """

        if self._direction is None:
            # Already neutral, so there is nothing to correct.
            self._still_since = None
            self._still_anchor = None
            return False

        anchor = self._still_anchor
        if anchor is None or hypot(nose[0] - anchor[0], nose[1] - anchor[1]) > self.thresholds.recentre_stillness:
            self._still_anchor = nose
            self._still_since = now
            return False

        started = self._still_since
        return started is not None and now - started >= self.thresholds.recentre_seconds

    def _state(
        self,
        *,
        offset: tuple[float, float],
        nose_point: tuple[float, float] | None,
        mouth_value: float | None,
        wink_value: float | None,
        mouth_fired: bool,
        wink_fired: bool,
        tracking: bool,
        now: float,
    ) -> dict[str, object]:
        direction = self._direction
        keys = list(DIRECTION_KEYS[direction]) if direction is not None else []
        return {
            "centered": direction is None,
            "nose": {"x": round(offset[0], 4), "y": round(offset[1], 4)},
            # Absolute positions in the mirrored camera image, so the overlay
            # can put the ball on the actual nose rather than in the middle of
            # the frame.
            "nose_point": _point(nose_point),
            "center_point": _point(self.center),
            "direction": direction,
            "keys": keys,
            "mouth": {
                "active": self._mouth.latched,
                "fired": mouth_fired,
                "value": mouth_value,
                "confidence": _confidence(mouth_value, self._mouth.on_value),
                "held_seconds": round(self._mouth.held_seconds(now), 3),
            },
            "wink": {
                "active": self._wink.latched,
                "fired": wink_fired,
                "value": wink_value,
                "confidence": _confidence(wink_value, self.thresholds.wink_on),
                "held_seconds": round(self._wink.held_seconds(now), 3),
                "eye": self._wink_eye,
            },
            "tracking": tracking,
            "recentred": self.recentred,
        }


ZONE_CENTERS: Mapping[Direction, float] = {
    "E": 0.0, "NE": 45.0, "N": 90.0, "NW": 135.0,
    "W": 180.0, "SW": 225.0, "S": 270.0, "SE": 315.0,
}


def _within_zone(offset: tuple[float, float], direction: Direction, margin: float) -> bool:
    """True when the offset still falls inside a zone widened by `margin`."""

    angle = degrees(atan2(-offset[1], offset[0])) % 360.0
    delta = abs((angle - ZONE_CENTERS[direction] + 180.0) % 360.0 - 180.0)
    return delta <= 22.5 + margin


def _point(value: tuple[float, float] | None) -> dict[str, float] | None:
    if value is None:
        return None
    return {"x": round(value[0], 4), "y": round(value[1], 4)}


def _wink_eye(signed: float | None, deadband: float) -> str | None:
    """Which eye is winking, or None when neither clearly is."""

    if signed is None or abs(signed) < deadband:
        return None
    return "left" if signed > 0 else "right"


def _confidence(value: float | None, threshold: float) -> float:
    """Progress toward a trigger threshold, clamped to [0, 1], for UI meters."""

    if value is None or threshold <= 0:
        return 0.0
    return max(0.0, min(value / threshold, 1.0))
