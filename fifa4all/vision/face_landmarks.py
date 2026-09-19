"""Thin wrapper around MediaPipe's FaceLandmarker (Tasks API).

MediaPipe 1.0 removed the legacy ``mp.solutions`` API, so we use the Tasks API
with a downloaded ``face_landmarker.task`` bundle. This module is the *only*
place that imports MediaPipe, which keeps the rest of the pipeline testable
without the native dependency.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "models",
    "face_landmarker.task",
)


@dataclass
class FaceResult:
    """Normalized output of a single detection, decoupled from MediaPipe types."""

    detected: bool
    transform_matrix: Optional[np.ndarray] = None
    blendshapes: dict[str, float] = field(default_factory=dict)
    num_landmarks: int = 0

    def blendshape(self, name: str, default: float = 0.0) -> float:
        return self.blendshapes.get(name, default)


class FaceLandmarkerWrapper:
    """Detect face landmarks, head-pose matrix and blendshapes from a BGR frame."""

    def __init__(self, model_path: str = DEFAULT_MODEL_PATH, num_faces: int = 1):
        if not os.path.isfile(model_path):
            raise FileNotFoundError(
                f"FaceLandmarker model not found at {model_path!r}. "
                "Run scripts/download_models.sh first."
            )
        # Imported lazily so importing this module never hard-fails when the
        # native library is unavailable (e.g. pure logic unit tests).
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self._mp = mp
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model_path),
            num_faces=num_faces,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)

    def detect(self, bgr_image: np.ndarray) -> FaceResult:
        import cv2

        rgb = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB, data=rgb
        )
        result = self._landmarker.detect(mp_image)
        if not result.face_landmarks:
            return FaceResult(detected=False)

        matrix = None
        if result.facial_transformation_matrixes:
            matrix = np.array(result.facial_transformation_matrixes[0])

        blendshapes: dict[str, float] = {}
        if result.face_blendshapes:
            blendshapes = {
                c.category_name: float(c.score) for c in result.face_blendshapes[0]
            }

        return FaceResult(
            detected=True,
            transform_matrix=matrix,
            blendshapes=blendshapes,
            num_landmarks=len(result.face_landmarks[0]),
        )

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> "FaceLandmarkerWrapper":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
