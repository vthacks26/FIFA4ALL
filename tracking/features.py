"""Geometry-based face movement feature extraction."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, hypot
from time import monotonic
from typing import Mapping, Sequence

from tracking.frames import FEATURE_UNITS, MovementFeature, MovementFrame


Point = tuple[float, float]

# Spans shorter than this fraction of the face width are landmark noise, not
# anatomy: the narrowest human mouth is still roughly a third of the face
# width and a hard pucker only halves that, and the inter-eye span never falls
# below a third of it on a face pointed anywhere near the camera. Dividing by a
# span below this floor produces a number with no physical meaning, so the
# measurements that use it as a denominator are reported unavailable instead.
MIN_SPAN_FRACTION = 0.10


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
    """Extract the supported movement features from face landmarks."""

    # Without these nothing is measurable, so a frame missing one is reported
    # as tracking lost rather than as a face with some features missing.
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

    # Landmarks that unlock extra gesture channels, kept optional so trackers
    # that emit only the core set keep producing a valid frame. A face without
    # these points yields an unavailable measurement for the features below,
    # never a silent zero that a threshold could read as "resting".
    OPTIONAL_FEATURE_LANDMARKS: Mapping[str, tuple[str, ...]] = {
        "brow_raise": ("left_brow", "right_brow"),
        "mouth_width": ("left_mouth_corner", "right_mouth_corner"),
        "mouth_pucker": ("left_mouth_corner", "right_mouth_corner"),
        "jaw_lateral": ("chin",),
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

        typed_points: dict[str, Point] = {
            name: point
            for name, point in points.items()
            if point is not None
            and (name in self.REQUIRED_LANDMARKS or name in _OPTIONAL_LANDMARKS)
        }
        raw = self._calculate(typed_points)
        features: dict[str, MovementFeature] = {
            name: MovementFeature.available_value(self._smooth(name, value), FEATURE_UNITS[name])
            for name, value in raw.items()
        }
        for name, unit in FEATURE_UNITS.items():
            if name in features:
                continue
            # Drop any stale smoothed history so a measurement that comes back
            # later cannot carry a value from before its landmarks vanished.
            self._smoothed.pop(name, None)
            features[name] = MovementFeature.unavailable(
                unit, self._missing_reason(name, typed_points)
            )
        return MovementFrame(timestamp_monotonic=timestamp, tracking_valid=True, features=features)

    def _missing_reason(self, name: str, points: Mapping[str, Point]) -> str:
        """Say why an optional measurement is absent this frame."""

        needed = self.OPTIONAL_FEATURE_LANDMARKS.get(name, ())
        absent = [landmark for landmark in needed if landmark not in points]
        if absent:
            return f"missing_landmarks:{','.join(absent)}"
        # Every landmark is present, so the span this measurement divides by
        # collapsed below MIN_SPAN_FRACTION.
        return f"degenerate_geometry:{name}"

    def _calculate(self, points: Mapping[str, Point]) -> dict[str, float]:
        face_width = _distance(points["left_cheek"], points["right_cheek"])
        if face_width < self.config.min_face_width:
            raise ValueError("face width too small for stable normalized measurements")

        min_span = face_width * MIN_SPAN_FRACTION
        nose = points["nose_tip"]
        left_eye = points["left_eye"]
        right_eye = points["right_eye"]

        mouth_opening = _distance(points["upper_lip"], points["lower_lip"]) / face_width

        cheek_mid_x = (points["left_cheek"][0] + points["right_cheek"][0]) / 2.0
        head_turn = (nose[0] - cheek_mid_x) / face_width

        eye_dx = right_eye[0] - left_eye[0]
        eye_dy = right_eye[1] - left_eye[1]
        head_tilt = degrees(atan2(eye_dy, eye_dx))

        left_eye_opening = _distance(points["left_upper_eyelid"], points["left_lower_eyelid"]) / face_width
        right_eye_opening = _distance(points["right_upper_eyelid"], points["right_lower_eyelid"]) / face_width
        left_wink = right_eye_opening - left_eye_opening

        eye_mid_y = (left_eye[1] + right_eye[1]) / 2.0
        # The nose tip sits below the eye line and protrudes toward the camera.
        # Pitching the chin up rotates that protrusion out of the image plane
        # and the gap shrinks; pitching it down rotates it in and the gap
        # grows. A first-order proxy, not an angle: roll shrinks it too, by
        # cos(roll), which is under 4% at the 15 degrees of head tilt a seated
        # player actually produces.
        head_pitch = (nose[1] - eye_mid_y) / face_width

        values: dict[str, float] = {
            "mouth_opening": mouth_opening,
            "head_turn": head_turn,
            "head_tilt": head_tilt,
            "head_pitch": head_pitch,
            "left_wink": left_wink,
            "left_eye_opening": left_eye_opening,
            "right_eye_opening": right_eye_opening,
        }

        eye_span = _distance(left_eye, right_eye)
        if eye_span >= min_span:
            # Cheek span measured against the inter-eye span rather than
            # against itself: face width *is* the cheek span, so it cannot be
            # its own normalizer. The eye corners are the nearest landmark
            # pair that a cheek puff does not move.
            values["cheek_span_ratio"] = face_width / eye_span

        left_brow = points.get("left_brow")
        right_brow = points.get("right_brow")
        if left_brow is not None and right_brow is not None:
            # Each brow against its own eye, then averaged, so a one-sided
            # raise still registers as half a raise instead of cancelling out.
            # Image y grows downward, so eye minus brow is positive.
            left_gap = left_eye[1] - left_brow[1]
            right_gap = right_eye[1] - right_brow[1]
            values["brow_raise"] = (left_gap + right_gap) / 2.0 / face_width

        left_corner = points.get("left_mouth_corner")
        right_corner = points.get("right_mouth_corner")
        if left_corner is not None and right_corner is not None:
            corner_span = _distance(left_corner, right_corner)
            values["mouth_width"] = corner_span / face_width
            if corner_span >= min_span:
                # Lip gap over mouth width: the aperture's aspect ratio. A
                # round "O" reads high, a closed resting mouth reads near
                # zero. Face width divides out of both terms, so this one
                # measurement is scale-free without normalizing at all.
                values["mouth_pucker"] = (
                    _distance(points["upper_lip"], points["lower_lip"]) / corner_span
                )

        chin = points.get("chin")
        if chin is not None and eye_span >= min_span:
            # Project chin-minus-nose onto the eye line, not onto the image x
            # axis. Both landmarks sit on the facial midline, so a head roll
            # swings them together: measured against image x, a 15 degree roll
            # over the ~0.35 face-width nose-to-chin span fakes a 0.09 offset,
            # about twice a real jaw slide. The eye line rolls with the head,
            # so projecting onto it removes roll to first order and what is
            # left is the jaw moving relative to the midline.
            axis = (
                (right_eye[0] - left_eye[0]) / eye_span,
                (right_eye[1] - left_eye[1]) / eye_span,
            )
            offset = (chin[0] - nose[0], chin[1] - nose[1])
            values["jaw_lateral"] = (offset[0] * axis[0] + offset[1] * axis[1]) / face_width

        return values

    def _smooth(self, name: str, value: float) -> float:
        alpha = self.config.smoothing_alpha
        if alpha >= 1.0 or name not in self._smoothed:
            self._smoothed[name] = value
        else:
            self._smoothed[name] = alpha * value + (1.0 - alpha) * self._smoothed[name]
        return self._smoothed[name]


_OPTIONAL_LANDMARKS: frozenset[str] = frozenset(
    landmark
    for landmarks in FaceFeatureExtractor.OPTIONAL_FEATURE_LANDMARKS.values()
    for landmark in landmarks
)


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])
