"""MediaPipe Face Mesh tracker (``mp.solutions``, mediapipe 0.10.x).

FaceLandmarker / Tasks (mediapipe 1.x) SIGABRTs on this Mac in Metal
(``DrishtiMetalHelper`` / ``graph_service.h:139``). This module is the *only*
place that imports MediaPipe, and it must not import ``mediapipe.tasks``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .features import FaceFeatures, extract_features
from .head_pose import HeadPose

# Map Face Mesh nose-offset units onto PR #1 degree dead zones.
# 0.18 yaw enter (Face Mesh) == 8° (HeadDirectionClassifier).
YAW_UNITS_TO_DEG = 8.0 / 0.18
# Face Mesh +pitch is look-up; PR #1 +pitch is look-down.
PITCH_UNITS_TO_DEG = 8.0 / 0.16


@dataclass
class FaceResult:
    """Normalized output of a single detection, decoupled from MediaPipe types."""

    detected: bool
    transform_matrix: Optional[np.ndarray] = None
    blendshapes: dict[str, float] = field(default_factory=dict)
    num_landmarks: int = 0
    features: Optional[FaceFeatures] = None

    def blendshape(self, name: str, default: float = 0.0) -> float:
        return self.blendshapes.get(name, default)


def head_pose_from_features(features: FaceFeatures) -> HeadPose:
    """Convert Face Mesh yaw/pitch units into PR #1 HeadPose degrees."""

    if not features.detected:
        return HeadPose(0.0, 0.0, 0.0)
    import math

    return HeadPose(
        yaw=features.yaw * YAW_UNITS_TO_DEG,
        pitch=-features.pitch * PITCH_UNITS_TO_DEG,
        roll=math.degrees(features.roll),
    )


class FaceMeshTracker:
    """Detect Face Mesh landmarks from a BGR frame using ``mp.solutions``."""

    def __init__(
        self,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        import mediapipe as mp

        if not hasattr(mp, "solutions"):
            raise RuntimeError(
                "mediapipe 1.x Tasks/FaceLandmarker SIGABRTs on this Mac. "
                "Install mediapipe>=0.10.14,<1 (mp.solutions Face Mesh)."
            )
        self._mp = mp
        self._mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def detect(self, bgr_image: np.ndarray) -> FaceResult:
        import cv2

        rgb = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        result = self._mesh.process(rgb)
        if not result.multi_face_landmarks:
            return FaceResult(detected=False)

        lm = result.multi_face_landmarks[0].landmark
        pts = np.array([[p.x, p.y] for p in lm], dtype=np.float32)
        features = extract_features(pts)
        return FaceResult(
            detected=True,
            blendshapes={"jawOpen": features.mouth_open},
            num_landmarks=len(lm),
            features=features,
        )

    def close(self) -> None:
        self._mesh.close()

    def __enter__(self) -> "FaceMeshTracker":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
