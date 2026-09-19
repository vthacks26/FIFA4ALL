"""Geometry-based face movement feature extraction."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, hypot
from time import monotonic
from typing import Mapping, Sequence

from tracking.frames import FEATURE_UNITS, MovementFeature, MovementFrame


Point = tuple[float, float]


@dataclass(frozen=True)
class FeatureConfig:
    """Configuration for feature extraction and smoothing.

    smoothing_alpha is an exponential smoothing factor in [0, 1].
    1.0 means no smoothing; lower values smooth more but add delay.
    """

    smoothing_alpha: float = 0.55
    min_face_width: float = 0.05

    def __post_init__(self) -> None:
        if not 0.0 <= self.smoothing_alpha <= 1.0:
            raise ValueError("smoothing_alpha must be between 0 and 1")
        if self.min_face_width <= 0:
            raise ValueError("min_face_width must be positive")


class FaceFeatureExtractor:
    """Extract the initial supported movement features from face landmarks."""

    REQUIRED_LANDMARKS = {
        "left_cheek",
        "right_cheek",
        "upper_lip",
        "lower_lip",
        "nose_tip",
        "left_eye",
        "right_eye",
        "left_upper_eyelid",
        "left_lower_eyelid",
        "right_upper_eyelid",
        "right_lower_eyelid",
    }

    def __init__(self, config: FeatureConfig | None = None) -> None:
        self.config = config or FeatureConfig()
        self._smoothed: dict[str, float] = {}

    def reset(self) -> None:
        self._smoothed.clear()

    def from_named_points(
        self,
        points: Mapping[str, Point | None],
        *,
        timestamp_monotonic: float | None = None,
        tracking_valid: bool = True,
    ) -> MovementFrame:
        """Build a MovementFrame from normalized 2D face landmark points."""

        timestamp = monotonic() if timestamp_monotonic is None else timestamp_monotonic
        missing = sorted(name for name in self.REQUIRED_LANDMARKS if points.get(name) is None)
        if not tracking_valid or missing:
            reason = "tracking_lost" if not tracking_valid else f"missing_landmarks:{','.join(missing)}"
            self.reset()
            return MovementFrame(
                timestamp_monotonic=timestamp,
                tracking_valid=False,
                features={
                    name: MovementFeature.unavailable(unit, reason)
                    for name, unit in FEATURE_UNITS.items()
                },
            )

        typed_points = {name: points[name] for name in self.REQUIRED_LANDMARKS}
        assert all(point is not None for point in typed_points.values())
        raw = self._calculate(typed_points)  # type: ignore[arg-type]
        features = {
            name: MovementFeature.available_value(self._smooth(name, value), FEATURE_UNITS[name])
            for name, value in raw.items()
        }
        return MovementFrame(timestamp_monotonic=timestamp, tracking_valid=True, features=features)

    def _calculate(self, points: Mapping[str, Point]) -> dict[str, float]:
        face_width = _distance(points["left_cheek"], points["right_cheek"])
        if face_width < self.config.min_face_width:
            raise ValueError("face width too small for stable normalized measurements")

        mouth_opening = _distance(points["upper_lip"], points["lower_lip"]) / face_width

        cheek_mid_x = (points["left_cheek"][0] + points["right_cheek"][0]) / 2.0
        head_turn = (points["nose_tip"][0] - cheek_mid_x) / face_width

        eye_dx = points["right_eye"][0] - points["left_eye"][0]
        eye_dy = points["right_eye"][1] - points["left_eye"][1]
        head_tilt = degrees(atan2(eye_dy, eye_dx))

        left_eye_opening = _distance(points["left_upper_eyelid"], points["left_lower_eyelid"]) / face_width
        right_eye_opening = _distance(points["right_upper_eyelid"], points["right_lower_eyelid"]) / face_width
        left_wink = right_eye_opening - left_eye_opening

        return {
            "mouth_opening": mouth_opening,
            "head_turn": head_turn,
            "head_tilt": head_tilt,
            "left_wink": left_wink,
            "left_eye_opening": left_eye_opening,
            "right_eye_opening": right_eye_opening,
        }

    def _smooth(self, name: str, value: float) -> float:
        alpha = self.config.smoothing_alpha
        if alpha >= 1.0 or name not in self._smoothed:
            self._smoothed[name] = value
        else:
            self._smoothed[name] = alpha * value + (1.0 - alpha) * self._smoothed[name]
        return self._smoothed[name]


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])
