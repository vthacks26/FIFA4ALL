"""MediaPipe Face Mesh tracker. Optional at import time so tests stay headless."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class FaceObservation:
    detected: bool
    landmarks: np.ndarray | None  # (N, 2) image-normalized x,y
    image_bgr: Any


class MediaPipeFaceTracker:
    def __init__(
        self,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        try:
            import mediapipe as mp
        except ImportError as exc:
            raise RuntimeError(
                "mediapipe is required for the live camera path. "
                "Install dependencies from requirements.txt."
            ) from exc

        self._mp = mp
        self._mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def process(self, frame_bgr: Any) -> FaceObservation:
        import cv2

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        result = self._mesh.process(rgb)
        if not result.multi_face_landmarks:
            return FaceObservation(False, None, frame_bgr)
        lm = result.multi_face_landmarks[0].landmark
        pts = np.array([[p.x, p.y] for p in lm], dtype=np.float32)
        return FaceObservation(True, pts, frame_bgr)

    def close(self) -> None:
        self._mesh.close()
