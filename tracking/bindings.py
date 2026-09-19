"""Action-to-gesture bindings.

Which movement triggers which game action is per-player data, not a constant.
`tracking.controls` owns how a gesture is detected; this module owns what a
detected gesture means. Keeping them apart is what lets orientation rebind an
action without touching detection.

Movement stays on the nose joystick for now. Only discrete actions are
bindable, because a nose offset is a continuous two-axis signal and an
expression is an event; they are not interchangeable.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Mapping

# How an action consumes its gesture.
#   hold: the key is held while the gesture is active. Shot power is duration.
#   tap:  the rising edge taps the key once. Holding never repeats it.
Trigger = Literal["hold", "tap"]

ActionName = Literal["SHOOT", "PASS"]


@dataclass(frozen=True)
class Action:
    """A game action a player can bind a movement to."""

    name: ActionName
    key: str
    trigger: Trigger
    label: str


ACTIONS: Mapping[ActionName, Action] = {
    "SHOOT": Action(name="SHOOT", key="Space", trigger="hold", label="Shoot"),
    "PASS": Action(name="PASS", key="L", trigger="tap", label="Pass"),
}


@dataclass(frozen=True)
class GestureChannel:
    """A candidate movement a player can perform on purpose.

    A channel is offered to players only when it satisfies all three parts of
    the eligibility rule in CUSTOM_CONTROLS_PLAN.md: a per-user resting value,
    a hysteresis pair, and a gate against its involuntary confound.

    Attributes:
        feature: Key in the feature mapping this channel reads.
        use_magnitude: Read abs(value). Signed features such as `left_wink`
            fire on either direction.
        required_features: Features that must be present. Missing any of them
            makes the channel unavailable rather than zero.
        default_on / default_off: Hysteresis pair before per-user calibration.
            default_off must be below default_on or the latch never releases.
        rest_feature: Feature sampled while the player sits neutral, used to
            lift thresholds clear of their resting value. None means this
            channel needs no resting baseline.
        gate: Named confound gate applied before triggering, or None when the
            channel has no involuntary confound. `one_eye_open` rejects a
            blink by requiring the other eye to stay open.
        selectable: False keeps a channel working without offering it during
            orientation.
    """

    name: str
    label: str
    feature: str
    required_features: tuple[str, ...]
    default_on: float
    default_off: float
    use_magnitude: bool = False
    rest_feature: str | None = None
    gate: str | None = None
    selectable: bool = True

    def __post_init__(self) -> None:
        if self.default_off >= self.default_on:
            raise ValueError(f"{self.name}: default_off must be below default_on")
        if self.default_on <= 0:
            raise ValueError(f"{self.name}: default_on must be positive")
        if self.feature not in self.required_features:
            raise ValueError(f"{self.name}: required_features must include {self.feature!r}")


# Seeded with exactly today's two working gestures so the default binding map
# reproduces current behaviour. New channels are added by Phase 3 and must
# satisfy the eligibility rule before setting selectable=True.
CHANNELS: Mapping[str, GestureChannel] = {
    "mouth_open": GestureChannel(
        name="mouth_open",
        label="Open your mouth",
        feature="mouth_opening",
        required_features=("mouth_opening",),
        default_on=0.090,
        default_off=0.060,
        rest_feature="mouth_opening",
    ),
    "wink": GestureChannel(
        name="wink",
        label="Wink one eye",
        feature="left_wink",
        required_features=("left_wink", "left_eye_opening", "right_eye_opening"),
        default_on=0.025,
        default_off=0.015,
        use_magnitude=True,
        rest_feature="left_eye_opening",
        gate="one_eye_open",
    ),
}


class BindingError(ValueError):
    """Raised when a binding map is not playable."""


@dataclass(frozen=True)
class BindingMap:
    """Which channel drives each action for one player."""

    bindings: Mapping[ActionName, str]

    def __post_init__(self) -> None:
        seen: dict[str, ActionName] = {}
        for action, channel in self.bindings.items():
            if action not in ACTIONS:
                raise BindingError(f"unknown action: {action}")
            if channel not in CHANNELS:
                raise BindingError(f"unknown channel: {channel}")
            if channel in seen:
                raise BindingError(
                    f"{channel!r} is bound to both {seen[channel]} and {action}; "
                    "one movement cannot drive two actions"
                )
            seen[channel] = action

    def channel_for(self, action: ActionName) -> GestureChannel | None:
        name = self.bindings.get(action)
        return None if name is None else CHANNELS[name]

    def action_for(self, channel_name: str) -> Action | None:
        for action, name in self.bindings.items():
            if name == channel_name:
                return ACTIONS[action]
        return None

    def rebound(self, action: ActionName, channel_name: str) -> "BindingMap":
        """Return a copy with `action` moved to `channel_name`.

        Any other action already holding that channel is left unbound rather
        than silently sharing it, so the caller has to rebind it deliberately.
        """

        updated = {a: c for a, c in self.bindings.items() if c != channel_name}
        updated[action] = channel_name
        return replace(self, bindings=updated)

    def as_dict(self) -> dict[str, str]:
        """Publish to the UI so drills and meters follow the live bindings."""

        return dict(self.bindings)


def default_bindings() -> BindingMap:
    """The mapping the game shipped with, used until orientation changes it."""

    return BindingMap(bindings={"SHOOT": "mouth_open", "PASS": "wink"})


def selectable_channels() -> tuple[GestureChannel, ...]:
    """Channels orientation may offer, in a stable order."""

    return tuple(c for c in CHANNELS.values() if c.selectable)
