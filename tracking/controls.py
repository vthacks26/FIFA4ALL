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

from tracking.bindings import CHANNELS, BindingMap, GestureChannel, default_bindings

Direction = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

# The state contract shipped with one top-level key per gesture, named after the
# gesture rather than after its channel. The frontend and `output.session` still
# read those names, so `_state` publishes each channel under both its channel
# name and its legacy alias. Phase 2 moves the last reader onto the channel view
# and this mapping goes away with it; until then the two must never diverge,
# which is why the alias is the same object, not a copy.
LEGACY_CHANNEL_KEYS: Mapping[str, str] = {
    "mouth_open": "mouth",
    "wink": "wink",
}

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
    # Raised eyebrows recentre pose (same ControlStateMachine.calibrate as
    # overlay RESET and POST /calibrate). Thresholds are deltas above the
    # resting brow-to-eyelid gap sampled on the first valid face and again
    # on click-calibrate. Hysteresis so a hold fires once. An open mouth
    # does not move the brows, so shoot cannot reset.
    brow_on: float = 0.030
    brow_off: float = 0.012
    # Eyelids do not close in sync, so mid-blink the left/right difference
    # spikes well past wink_on and reads as a wink. Measured on a real blink:
    # left 0.0043 against right 0.0551, a difference of 0.0508, double the
    # threshold. What separates the two is the other eye: during a wink it
    # stays properly open, during a blink it is already closing. A wink is
    # only accepted while the open eye is above this fraction of the openness
    # measured for this user at calibration.
    eye_open_fraction: float = 0.65
    # Used until calibration measures the user. Typical open eye reads ~0.10.
    eye_open_floor: float = 0.070
    # Head pitch moves the brow-to-eye gap by a few percent on its own, and
    # pitching is not idle fidgeting in this game: it is the N/S steering axis
    # of the nose joystick. A brow raise is only accepted while pitch is within
    # this much of the value measured for this user at calibration, so steering
    # cannot trip it.
    pitch_level_band: float = 0.060
    # The chin sits further from the axis of rotation than the nose tip, so a
    # head turn leaves a residual lateral chin offset in the direction of the
    # turn. A jaw slide is only accepted while the head is this close to
    # forward. Expressed in head_turn units, which measure the nose against the
    # cheek midpoint -- deliberately NOT reusing enter_radius, which measures a
    # different thing (nose offset from the calibrated centre) and would be a
    # silent unit error.
    facing_forward_turn: float = 0.060
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
        if self.brow_off >= self.brow_on:
            raise ValueError("brow_off must be below brow_on")
        if not 0.0 < self.eye_open_fraction < 1.0:
            raise ValueError("eye_open_fraction must be between 0 and 1")
        if self.pitch_level_band <= 0:
            raise ValueError("pitch_level_band must be positive")
        if self.facing_forward_turn <= 0:
            raise ValueError("facing_forward_turn must be positive")
        if self.eye_open_floor <= 0:
            raise ValueError("eye_open_floor must be positive")
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
            "brow_on": self.brow_on,
            "brow_off": self.brow_off,
            "eye_open_fraction": self.eye_open_fraction,
            "eye_open_floor": self.eye_open_floor,
            "pitch_level_band": self.pitch_level_band,
            "facing_forward_turn": self.facing_forward_turn,
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
    # Which channel drives which action. Detection does not depend on it - every
    # channel is measured every frame whether or not it is bound, because an
    # orientation drill has to watch a gesture before it owns an action. The map
    # rides along so that everything reading the stream resolves action ->
    # channel against the same bindings the machine is running under.
    bindings: BindingMap = field(default_factory=default_bindings)
    center: tuple[float, float] | None = None
    mouth_rest: float | None = None
    eye_rest: float | None = None
    brow_rest: float | None = None
    auto_recentre: bool = True
    recentred: bool = False
    _moving: bool = False
    _direction: Direction | None = None
    _still_since: float | None = None
    _still_anchor: tuple[float, float] | None = None
    _wink_eye: str | None = None
    pitch_rest: float | None = None
    _mouth: _EdgeTrigger = field(init=False)
    _wink: _EdgeTrigger = field(init=False)
    _extra: dict[str, _EdgeTrigger] = field(init=False)
    _brow: _EdgeTrigger = field(init=False)

    def __post_init__(self) -> None:
        self._mouth = _EdgeTrigger(self.thresholds.mouth_open, self.thresholds.mouth_reset)
        self._wink = _EdgeTrigger(self.thresholds.wink_on, self.thresholds.wink_off)
        # Every other registered channel gets a trigger built from its own
        # declared thresholds. Channels are measured whether or not they are
        # bound, because orientation has to see a gesture nobody selected yet
        # in order to offer it.
        self._extra = {
            name: _EdgeTrigger(channel.default_on, channel.default_off)
            for name, channel in CHANNELS.items()
            if name not in ("mouth_open", "wink")
        }
        # Until a resting brow gap is sampled, keep the trigger above any
        # realistic value so a hold cannot fire on the first unseen face.
        self._brow = _EdgeTrigger(1.0, 0.9)

    def calibrate(
        self,
        nose: tuple[float, float] | None,
        *,
        mouth_rest: float | None = None,
        eye_rest: float | None = None,
        pitch_rest: float | None = None,
        brow_rest: float | None = None,
    ) -> None:
        """Set the neutral centre, and optionally resting expression baselines.

        `mouth_rest` is the mouth-opening ratio measured while the user sits
        neutral. It raises the release threshold clear of that value so the
        shoot latch cannot stick open. `brow_rest` is the brow-to-eyelid gap
        at the same pose; gesture reset does not pass it, because raised
        brows are not a resting face.
        """

        self.center = nose
        if mouth_rest is not None:
            self.mouth_rest = mouth_rest
            self._apply_mouth_thresholds()
        if eye_rest is not None:
            self.eye_rest = eye_rest
        if pitch_rest is not None:
            self.pitch_rest = pitch_rest
        if brow_rest is not None:
            self.brow_rest = brow_rest
            self._apply_brow_thresholds()
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
            lost = {
                name: self._channel_state(CHANNELS[name], {}, moment, tracking=False)
                for name in self._extra
            }
            self._brow.update(None, moment)
            return self._state(
                offset=(0.0, 0.0),
                nose_point=None,
                mouth_value=None,
                wink_value=None,
                brow_value=None,
                mouth_fired=False,
                wink_fired=False,
                brow_fired=False,
                tracking=False,
                now=moment,
                extra_channels=lost,
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

        # `left_wink` is signed: positive when the left eye is more closed,
        # negative when the right eye is. Magnitude is what matters, so either
        # eye triggers a pass. Blinking both eyes moves them together and
        # leaves the difference near zero, so it still does not fire.
        signed_wink = features.get("left_wink")
        wink_value = None if signed_wink is None else abs(signed_wink)
        if wink_value is not None and not self._one_eye_still_open(features):
            # Both eyes are closing: this is a blink, not a wink.
            wink_value = 0.0
        self._wink_eye = (
            None if wink_value == 0.0 else _wink_eye(signed_wink, self.thresholds.wink_off)
        )
        brow_value = features.get("eyebrow_raise")
        if self.brow_rest is None and brow_value is not None:
            # First valid face, same idea as first-frame pose centre: this is
            # rest, not a raise, so do not fire on this frame.
            self.brow_rest = brow_value
            self._apply_brow_thresholds()
        _, brow_fired = self._brow.update(
            None if self.brow_rest is None else brow_value, moment
        )
        if brow_fired:
            # Same pose reset as overlay RESET / POST /calibrate, but do not
            # sample mouth_rest or brow_rest: the brows are raised.
            self.calibrate(nose)
            offset = (0.0, 0.0)
            self._update_movement(offset)
        mouth_value = features.get("mouth_opening")
        _, mouth_fired = self._mouth.update(mouth_value, moment)
        _, wink_fired = self._wink.update(wink_value, moment)
        extra = {
            name: self._channel_state(CHANNELS[name], features, moment, tracking=True)
            for name in self._extra
        }

        return self._state(
            offset=offset,
            nose_point=nose,
            mouth_value=features.get("mouth_opening"),
            wink_value=wink_value,
            brow_value=brow_value,
            mouth_fired=mouth_fired,
            wink_fired=wink_fired,
            brow_fired=brow_fired,
            tracking=True,
            now=moment,
            extra_channels=extra,
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

    def eye_open_gate(self) -> float:
        """Openness the non-winking eye must clear for a wink to count."""

        if self.eye_rest is None:
            return self.thresholds.eye_open_floor
        return max(
            self.thresholds.eye_open_floor * 0.5,
            self.eye_rest * self.thresholds.eye_open_fraction,
        )

    def gate_passes(self, channel: GestureChannel, features: Mapping[str, float]) -> bool:
        """Whether a channel's confound gate allows it to fire this frame.

        A gate answers one question: could this reading be the channel's known
        confound rather than the gesture? When the gate cannot be evaluated --
        a missing feature, or a baseline this player never calibrated -- the
        answer is no. Firing on an unevaluable gate would hand the player an
        action that triggers itself, which is the failure this whole mechanism
        exists to prevent.
        """

        gate = channel.gate
        if gate is None:
            return True
        if gate == "one_eye_open":
            # A blink closes both lids together; a wink leaves one eye open.
            return self._one_eye_still_open(features)
        if gate == "head_level":
            pitch = features.get("head_pitch")
            if pitch is None or self.pitch_rest is None:
                return False
            return abs(pitch - self.pitch_rest) <= self.thresholds.pitch_level_band
        if gate == "mouth_near_rest":
            mouth = features.get("mouth_opening")
            if mouth is None:
                return False
            # Reuse the shoot release threshold rather than inventing another
            # number: a mouth open enough to still be holding a shot is by
            # definition not a resting mouth, so it cannot also be a smile.
            return mouth <= self._mouth.off_value
        if gate == "facing_forward":
            turn = features.get("head_turn")
            if turn is None:
                return False
            return abs(turn) <= self.thresholds.facing_forward_turn
        # An unknown gate is a programming error, not a runtime condition.
        # Passing it silently would ship a channel with no guard at all.
        raise ValueError(f"unknown confound gate: {gate!r} on channel {channel.name!r}")

    def _channel_state(
        self,
        channel: GestureChannel,
        features: Mapping[str, float],
        now: float,
        *,
        tracking: bool,
    ) -> dict[str, object]:
        """Measure one registered channel and advance its trigger."""

        trigger = self._extra[channel.name]
        if not tracking:
            trigger.update(None, now)
            return _channel_view(trigger, value=None, fired=False, gated=False, now=now)

        missing = any(features.get(name) is None for name in channel.required_features)
        if missing:
            # A landmark this channel needs is absent. Release rather than read
            # a missing measurement as a resting value.
            trigger.update(None, now)
            return _channel_view(trigger, value=None, fired=False, gated=False, now=now)

        raw = features.get(channel.feature)
        value = None if raw is None else (abs(raw) if channel.use_magnitude else raw)
        gated = not self.gate_passes(channel, features)
        if gated:
            # The gate rejected this frame, so the reading may be the confound.
            # Drive the trigger to release; the UI is told why below.
            trigger.update(None, now)
            return _channel_view(trigger, value=value, fired=False, gated=True, now=now)
        _, fired = trigger.update(value, now)
        return _channel_view(trigger, value=value, fired=fired, gated=False, now=now)

    def _one_eye_still_open(self, features: Mapping[str, float]) -> bool:
        """True when one eye is clearly open, which a blink never satisfies."""

        left = features.get("left_eye_opening")
        right = features.get("right_eye_opening")
        if left is None or right is None:
            # Without absolute openings we cannot tell the two apart; keep the
            # previous behaviour rather than silently dropping every wink.
            return True
        return max(left, right) >= self.eye_open_gate()

    def _apply_mouth_thresholds(self) -> None:
        """Lift the mouth thresholds clear of this person's resting value."""

        rest = self.mouth_rest
        if rest is None:
            return
        reset = max(self.thresholds.mouth_reset, rest + self.thresholds.mouth_rest_clearance)
        self._mouth.off_value = reset
        self._mouth.on_value = max(self.thresholds.mouth_open, reset + self.thresholds.mouth_min_gap)

    def _apply_brow_thresholds(self) -> None:
        """Place the raise trigger a delta above this person's resting gap."""

        rest = self.brow_rest
        if rest is None:
            return
        self._brow.off_value = rest + self.thresholds.brow_off
        self._brow.on_value = rest + self.thresholds.brow_on

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
        brow_value: float | None,
        mouth_fired: bool,
        wink_fired: bool,
        brow_fired: bool,
        tracking: bool,
        now: float,
        extra_channels: Mapping[str, dict[str, object]] | None = None,
    ) -> dict[str, object]:
        direction = self._direction
        keys = list(DIRECTION_KEYS[direction]) if direction is not None else []
        # Built once and shared, so the channel view and the legacy alias below
        # can never report different values for the same gesture.
        channels: dict[str, object] = {
            "mouth_open": {
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
        }
        # Channels beyond the original two, measured the same way and merged in
        # so a drill can read any of them by name.
        channels.update(extra_channels or {})
        state: dict[str, object] = {
            "centered": direction is None,
            "nose": {"x": round(offset[0], 4), "y": round(offset[1], 4)},
            # Absolute positions in the mirrored camera image, so the overlay
            # can put the ball on the actual nose rather than in the middle of
            # the frame.
            "nose_point": _point(nose_point),
            "center_point": _point(self.center),
            "direction": direction,
            "keys": keys,
            # Every measured gesture, keyed by channel name. A drill reads the
            # channel it is watching without knowing which action owns it.
            "channels": channels,
            # The map the caller should resolve actions against, published with
            # the frame it applied to so a rebind can never be read a frame late.
            "bindings": self.bindings.as_dict(),
            "eyebrow": {
                "active": self._brow.latched,
                "fired": brow_fired,
                "value": brow_value,
                "confidence": _confidence(
                    None
                    if brow_value is None or self.brow_rest is None
                    else max(brow_value - self.brow_rest, 0.0),
                    self.thresholds.brow_on,
                ),
                "held_seconds": round(self._brow.held_seconds(now), 3),
            },
            "tracking": tracking,
            "recentred": self.recentred,
        }
        for channel_name, legacy_key in LEGACY_CHANNEL_KEYS.items():
            state[legacy_key] = channels[channel_name]
        return state


ZONE_CENTERS: Mapping[Direction, float] = {
    "E": 0.0, "NE": 45.0, "N": 90.0, "NW": 135.0,
    "W": 180.0, "SW": 225.0, "S": 270.0, "SE": 315.0,
}


def _within_zone(offset: tuple[float, float], direction: Direction, margin: float) -> bool:
    """True when the offset still falls inside a zone widened by `margin`."""

    angle = degrees(atan2(-offset[1], offset[0])) % 360.0
    delta = abs((angle - ZONE_CENTERS[direction] + 180.0) % 360.0 - 180.0)
    return delta <= 22.5 + margin


def _channel_view(
    trigger: _EdgeTrigger,
    *,
    value: float | None,
    fired: bool,
    gated: bool,
    now: float,
) -> dict[str, object]:
    """One channel's slice of the state contract.

    `gated` is published so the UI can say why a gesture it can plainly see is
    not firing, for example that the player is mid-turn. Without it a gated
    channel looks identical to a broken one.
    """

    return {
        "active": trigger.latched,
        "fired": fired,
        "value": value,
        "confidence": 0.0 if gated else _confidence(value, trigger.on_value),
        "held_seconds": round(trigger.held_seconds(now), 3),
        "gated": gated,
    }


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


def hold_labels(state: Mapping[str, object]) -> list[str]:
    """WASD + Space hold + L hold from one control-state frame."""

    labels: list[str] = []
    keys = state.get("keys")
    if isinstance(keys, list):
        labels.extend(str(key) for key in keys if key in {"W", "A", "S", "D"})
    mouth = state.get("mouth")
    if isinstance(mouth, dict) and mouth.get("active"):
        labels.append("Space")
    wink = state.get("wink")
    if isinstance(wink, dict) and wink.get("active"):
        labels.append("L")
    return labels
