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
    "left_wink": "ratio_delta",
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
        "sensitive to glasses, lighting, and partial occlusion."
    ),
}
