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
    # How long the gesture must be held before the key goes down. Stops a
    # brief gesture starting a charge at all. It belongs to the action rather
    # than the gesture, so an action keeps its feel wherever it is rebound.
    press_delay_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.press_delay_seconds < 0:
            raise ValueError(f"{self.name}: press_delay_seconds cannot be negative")


ACTIONS: Mapping[ActionName, Action] = {
    # 200ms before Space goes down, so a brief mouth-open never starts FIFA's
    # charge curve. Once down it stays down; the curve is not pulsed or slowed.
    "SHOOT": Action(
        name="SHOOT", key="Space", trigger="hold", label="Shoot",
        press_delay_seconds=0.2,
    ),
    # Pass is a hold, not a tap: the wink holds L until the eye opens again.
    # 200ms before L goes down, matching shoot, so a brief wink never starts
    # a pass. Once down it stays down while the wink is held. The `tap`
    # trigger stays in the contract because it is still a legitimate shape
    # for an action, just not one any action uses today.
    "PASS": Action(
        name="PASS", key="L", trigger="hold", label="Pass",
        press_delay_seconds=0.2,
    ),
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
            blink by requiring the other eye to stay open, and rejects a
            tilt- or turn-covered eye that would otherwise look like a wink.
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


# The first two entries are exactly today's working gestures, so the default
# binding map reproduces current behaviour. Everything after them is Phase 3
# vocabulary and must satisfy the eligibility rule before setting
# selectable=True.
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
        # Blink: the other eye must stay open. Pose: a roll or yaw that
        # hides one eye is not a wink. Both live in `one_eye_open`.
        gate="one_eye_open",
    ),
    # --- Phase 3 channels -------------------------------------------------
    #
    # A `gate` is a name, not an implementation: detection lives in
    # tracking.controls, which owns the numeric band each gate compares
    # against, exactly as `one_eye_open` reads `eye_open_fraction` there. What
    # a channel owes the reader here is the confound it is guarding against
    # and why the named companion signal separates the two. Each channel's
    # companion is listed in `required_features`, so a gate can never be
    # evaluated against a measurement that is not on the frame.
    #
    # Two of these ship with selectable=False. A channel that fires by
    # accident mid-match is worse than a channel nobody can pick.
    "brow_raise": GestureChannel(
        name="brow_raise",
        label="Raise your eyebrows",
        feature="brow_raise",
        # head_pitch is the gate's companion, not part of the measurement.
        required_features=("brow_raise", "head_pitch"),
        # Resting brow-to-eye gap runs about 0.185 face widths; a deliberate
        # raise adds roughly a quarter of that gap. Trigger at rest + 0.05,
        # release at rest + 0.02, which is wide enough to clear the ~0.01 of
        # frame-to-frame wobble the smoothed signal carries. Both numbers are
        # anatomy-derived starting points, not tester measurements: brow shape
        # and glasses frames move the resting value enough that only the
        # rest sample below makes them safe.
        default_on=0.235,
        default_off=0.205,
        rest_feature="brow_raise",
        # Confound: head pitch. Nodding is not an idle habit here, it is the
        # steering axis -- the nose joystick's N/S motion is the player
        # tilting their head. Pitch moves this measurement two ways at once:
        # the gap is measured along image y so it shrinks by cos(pitch), and
        # the brow ridge protrudes, so rotating it in or out of the image
        # plane moves it again. Together that is several percent of the gap
        # against the ~25% a real raise produces -- not enough to swamp the
        # signal, but enough to trip a threshold set close to rest, and it
        # would trip it precisely while the player is steering, which is the
        # worst possible moment. The gate requires head_pitch to sit inside a
        # band around its calibrated resting value, so a brow raise only
        # counts while the head is level. Eye opening also correlates with a
        # brow raise, but it correlates in the direction that makes the
        # gesture more visible, not less, so it is not gated: a blink cannot
        # fake a brow raise because eyelids do not move the brow ridge.
        gate="head_level",
        # Held back from selection, not because the measurement is weak but
        # because the gesture is already taken: raising the eyebrows is the
        # pose-reset gesture on main. Binding it to an action as well would
        # recentre the player's neutral position every time they used it.
        # Still measured, so Phase 4 scoring can see it and so the channel is
        # ready if reset moves to another gesture. That is a product call.
        selectable=False,
    ),
    "smile_width": GestureChannel(
        name="smile_width",
        label="Smile wide",
        feature="mouth_width",
        required_features=("mouth_width", "mouth_opening"),
        # Resting mouth corners sit about 0.46 face widths apart; a broad
        # smile adds roughly 15%, so about 0.07. Trigger at rest + 0.07 and
        # release at rest + 0.035, half the excursion, so the latch clears
        # well before the corners are back to neutral. Anatomy-derived, and
        # mouth width varies more between faces than almost any other feature
        # here, which is what the rest sample is for.
        default_on=0.530,
        default_off=0.495,
        rest_feature="mouth_width",
        # Confound: a yawn or a laugh-with-jaw-drop, which is the involuntary
        # version of this gesture and also the movement already bound to
        # SHOOT. A jaw drop is not a neutral event for this measurement --
        # dropping the jaw narrows the corner separation slightly while the
        # lips stretch, so the raw number moves and the two channels are
        # reading the same four landmarks. The gate requires mouth_opening to
        # stay near its calibrated resting value, so a smile only counts with
        # the lips together. That gate does double duty: it is also what stops
        # smile_width and mouth_open co-firing when a player has both bound.
        # Head yaw is deliberately not gated. Yaw foreshortens the corner
        # separation faster than it foreshortens the cheek span used to
        # normalize it, so a turned head reads *narrower*: it loses smiles,
        # it cannot invent one, and a missed pass beats a pass nobody asked
        # for.
        gate="mouth_near_rest",
    ),
    "jaw_lateral": GestureChannel(
        name="jaw_lateral",
        label="Slide your jaw to one side",
        feature="jaw_lateral",
        required_features=("jaw_lateral", "head_turn"),
        # Signed: the chin slides either way and both are the same gesture.
        use_magnitude=True,
        # A comfortable lateral excursion is about 10mm on a 140mm face, so
        # 0.07 face widths. Trigger at 0.045, roughly two thirds of that, so a
        # limited jaw still reaches it; release at 0.030. Unlike the other
        # channels this one is built to read near zero at rest, so these are
        # excursions rather than absolute positions.
        default_on=0.045,
        default_off=0.030,
        # Rest is near zero but not at zero: a resting jaw sits a little off
        # the midline on most faces, and the landmark itself is biased by
        # whatever the mesh thinks the chin tip is. Sampling it turns the
        # thresholds into a real excursion from this player's neutral rather
        # than from an idealized centred chin.
        rest_feature="jaw_lateral",
        # Confound: head yaw, which is also the E/W steering axis. Most of it
        # is already removed by construction -- the measurement is the chin
        # against the *nose*, both on the midline, projected onto the eye
        # line, so roll cancels exactly and yaw cancels to first order. What
        # survives is second order: the chin sits further from the neck's axis
        # of rotation than the nose tip does, so a real turn leaves a residual
        # chin offset in the direction of the turn. That residual grows with
        # the turn, and the turn is exactly what the player does to steer, so
        # the gate requires head_turn to be inside the steering dead zone.
        # A jaw slide made while facing forward is accepted; one made mid-turn
        # is thrown away rather than guessed at.
        gate="facing_forward",
    ),
    "cheek_puff": GestureChannel(
        name="cheek_puff",
        label="Puff out your cheeks",
        feature="cheek_span_ratio",
        required_features=("cheek_span_ratio",),
        # Resting cheek-to-eye span ratio is about 2.05. A puff adds one or
        # two percent, so about 0.04. These thresholds exist so the channel is
        # measurable for Phase 4 scoring; they are not offered to players.
        default_on=2.150,
        default_off=2.100,
        rest_feature="cheek_span_ratio",
        # NOT SELECTABLE, and there is no honest gate to add.
        #
        # A cheek puff is out-of-plane bulge. The 2D landmark set sees the
        # silhouette, so it sees a percent or two of widening -- the same
        # order as the noise on the landmarks themselves, and smaller than the
        # change head yaw makes to the identical measurement. Worse, the
        # landmarks that would report the bulge (the cheek contour) are the
        # face-width normalizer every other feature divides by, so this is the
        # one gesture that cannot be normalized against the face at all; the
        # inter-eye span is used instead, which is a stiffer reference but a
        # much shorter one, so its own landmark noise is amplified.
        #
        # The confound here is therefore head yaw, and there is no gate worth
        # writing for it: yaw's effect on this measurement is larger than the
        # gesture's, so gating on head_turn would not be a guard, it would be
        # the only thing the channel responds to. A player who could puff
        # their cheeks reliably would still get a channel that fires when they
        # glance at the scoreboard. Shipping it selectable would be shipping a
        # random trigger. Revisit only with a depth signal or the MediaPipe
        # blendshape output, which measures the puff directly.
        selectable=False,
    ),
    "mouth_pucker": GestureChannel(
        name="mouth_pucker",
        label="Purse your lips into an O",
        feature="mouth_pucker",
        # The two channels it is arithmetically built from, so Phase 4 can see
        # the co-fire rather than having to infer it.
        required_features=("mouth_pucker", "mouth_opening", "mouth_width"),
        # A closed resting mouth reads about 0.03 and a round "O" about 0.20.
        # Trigger at 0.160 and release at 0.110, measurable for Phase 4
        # scoring but not offered to players.
        default_on=0.160,
        default_off=0.110,
        rest_feature="mouth_pucker",
        # NOT SELECTABLE. The confound is mouth_open, and it is structural.
        #
        # This measurement is lip gap over corner separation. A pucker raises
        # it by shrinking the denominator. A jaw drop raises it by growing the
        # numerator. They arrive at the same number from opposite directions,
        # and the numerator is literally the signal the default SHOOT binding
        # reads, so a pucker channel bound to PASS would fire every time the
        # player shot. Gating on mouth_opening staying near rest does not
        # rescue it either: a real "O" parts the lips, so that gate rejects
        # the gesture along with the confound.
        #
        # What actually separates a pucker from an open mouth is lip
        # protrusion -- the lips come toward the camera. That is depth, and it
        # is not in these 2D landmarks at any threshold. The same applies to
        # the corner separation it shares with smile_width, which it moves in
        # the opposite direction: one measurement cannot drive two channels
        # that disagree about which way is "on". Revisit with the MediaPipe
        # mouthPucker blendshape, which is trained on exactly this.
        selectable=False,
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
