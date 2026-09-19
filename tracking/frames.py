"""Frame and feature value containers emitted by tracking.

Person 3 owns the canonical shared interfaces. Until those are published,
this module keeps tracking output in the agreed minimal MovementFrame shape:
monotonic timestamp, tracking validity, and named movement features with
documented units. Missing measurements are represented as unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class MovementFeature:
    """A single movement measurement.

    Attributes:
        value: Numeric measurement. None means unavailable, not zero.
        unit: Unit string documented by the feature extractor.
        available: Whether this measurement is valid for this frame.
        reason: Optional human-readable reason for unavailability.
    """

    value: float | None
    unit: str
    available: bool
    reason: str | None = None

    @classmethod
    def available_value(cls, value: float, unit: str) -> "MovementFeature":
        return cls(value=float(value), unit=unit, available=True)

    @classmethod
    def unavailable(cls, unit: str, reason: str) -> "MovementFeature":
        return cls(value=None, unit=unit, available=False, reason=reason)


@dataclass(frozen=True)
class MovementFrame:
    """Movement measurements for one fresh video frame."""

    timestamp_monotonic: float
    tracking_valid: bool
    features: Mapping[str, MovementFeature]

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))


FEATURE_UNITS: Mapping[str, str] = {
    "mouth_opening": "ratio",
    "head_turn": "normalized_x_offset",
    "head_tilt": "degrees",
    "head_pitch": "normalized_y_offset",
    "left_wink": "ratio_delta",
    "left_eye_opening": "ratio",
    "right_eye_opening": "ratio",
    "brow_raise": "ratio",
    "mouth_width": "ratio",
    "mouth_pucker": "ratio",
    "jaw_lateral": "normalized_x_offset",
    "cheek_span_ratio": "ratio",
    "eyebrow_raise": "ratio",
}

FEATURE_DOCUMENTATION = {
    "mouth_opening": (
        "Vertical distance between upper and lower lip landmarks divided by "
        "face width. Larger positive values mean a more open mouth. This is "
        "sensitive to lip occlusion, facial hair, and extreme head turns."
    ),
    "head_turn": (
        "Horizontal nose-tip offset from the midpoint between cheek landmarks, "
        "divided by face width. Positive values mean the nose moved toward the "
        "user's right in the camera image. This is a coarse 2D proxy, not a "
        "true yaw angle."
    ),
    "head_tilt": (
        "Angle of the eye-line in degrees. Positive values mean the user's "
        "right eye appears lower in the camera image. This assumes the camera "
        "is approximately level."
    ),
    "left_wink": (
        "Right-eye openness minus left-eye openness, each normalized by face "
        "width. Larger positive values mean the user's left eye appears more "
        "closed than the right. This is a rough diagnostic measurement and is "
        "sensitive to glasses, lighting, and partial occlusion. On its own it "
        "cannot separate a wink from a blink, because eyelids do not close in "
        "sync: mid-blink this difference spikes. Pair it with the absolute "
        "openings below."
    ),
    "left_eye_opening": (
        "Left eyelid gap divided by face width. Around 0.10 with the eye open "
        "and near 0.00 closed, varying by face, so compare against a value "
        "measured for this user rather than a constant."
    ),
    "right_eye_opening": (
        "Right eyelid gap divided by face width. Same scale and caveats as "
        "left_eye_opening."
    ),
    "head_pitch": (
        "Vertical nose-tip offset below the eye line, divided by face width. "
        "Larger values mean the chin has dropped toward the chest; smaller "
        "values mean the chin has come up. The nose protrudes toward the "
        "camera, so pitch rotates that protrusion into or out of the image "
        "plane, which is what moves this number. It is a proxy, not an angle, "
        "and it cannot tell pitch apart from the user sliding up or down in "
        "their seat far enough to change the camera's viewing angle. Roll "
        "shrinks it by cos(roll) as well."
    ),
    "brow_raise": (
        "Mean brow-to-eye vertical gap divided by face width, averaged over "
        "the two sides. Larger values mean the brows are raised. Resting is "
        "around 0.18 but varies enough between faces, and with brow shape and "
        "glasses frames, that it must be compared against a value measured "
        "for this user. Roll shrinks it by cos(roll) because the gap is "
        "measured along image y, and head pitch moves it by several percent "
        "in its own right, which is why the brow_raise channel is gated on "
        "head_pitch."
    ),
    "mouth_width": (
        "Distance between the mouth corners divided by face width. Resting is "
        "around 0.46 on a relaxed face; a broad smile adds roughly 15%. "
        "Head yaw foreshortens the corner separation faster than it "
        "foreshortens the cheek span used to normalize it, so a turned head "
        "reads narrower than it is. That direction only loses smiles, it does "
        "not invent them. A jaw drop narrows this measurement slightly, so a "
        "wide open mouth is not a smile."
    ),
    "mouth_pucker": (
        "Lip gap divided by mouth-corner separation: the aspect ratio of the "
        "mouth aperture. Face width cancels out of both terms, so this is "
        "scale-free on its own. A closed resting mouth reads near 0.03 and a "
        "round 'O' reads around 0.20. It cannot on its own separate a pucker "
        "from a small jaw drop, because both raise the ratio: a jaw drop "
        "raises the numerator while a pucker shrinks the denominator. Lip "
        "protrusion, which is what actually distinguishes the two, is "
        "out-of-plane motion and is not observable in these 2D landmarks."
    ),
    "jaw_lateral": (
        "Chin offset from the nose tip, projected onto the eye line and "
        "divided by face width. Positive values mean the chin slid toward the "
        "user's right in the camera image. Near 0.00 at rest; a comfortable "
        "lateral excursion is roughly 0.07. Projecting onto the eye line "
        "rather than image x removes head roll, since both landmarks sit on "
        "the facial midline and swing together under roll. Head yaw is not "
        "removed: the chin is further from the axis of rotation than the nose "
        "tip, so a turn leaves a residual offset in the same direction as the "
        "turn, which is why the jaw_lateral channel is gated on head_turn."
    ),
    "cheek_span_ratio": (
        "Cheek-to-cheek distance divided by the inter-eye distance. Around "
        "2.05, varying with face shape. Face width cannot normalize a cheek "
        "measurement because face width is that measurement, so the eye "
        "corners are used as the reference instead. A cheek puff is mostly "
        "out-of-plane bulge, so it moves this number by only a percent or "
        "two, comparable to the shift head yaw produces. Treat it as a weak "
        "diagnostic, not a trigger."
    ),
    "eyebrow_raise": (
        "Average vertical gap from the inner/outer brows to the upper eyelids, "
        "divided by face width. Larger values mean the brows sit higher. An "
        "open mouth does not move these landmarks, so shoot cannot look like a "
        "reset. Sensitive to glasses, bangs, and extreme head pitch."
    ),
}
