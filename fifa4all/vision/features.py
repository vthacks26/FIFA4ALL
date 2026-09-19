"""Public MediaPipe Face Mesh indices and feature extraction.

Indices are from Google's public Face Mesh topology (468 points). Left/right
are the person's anatomical left/right.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

NOSE_TIP = 1
CHIN = 152
RIGHT_EYE_OUTER = 33
RIGHT_EYE_INNER = 133
LEFT_EYE_OUTER = 263
LEFT_EYE_INNER = 362
MOUTH_LEFT = 291
MOUTH_RIGHT = 61
MOUTH_UPPER = 13
MOUTH_LOWER = 14

# Eye aspect ratio: outer, upper, upper, inner, lower, lower
RIGHT_EAR_IDX = (33, 160, 158, 133, 153, 144)
LEFT_EAR_IDX = (362, 385, 387, 263, 373, 380)

LANDMARK_COUNT = 468


@dataclass(frozen=True)
class FaceFeatures:
    detected: bool
    yaw: float = 0.0  # + = nose toward image +x (right after optional mirror)
    pitch: float = 0.0  # + = looking up (nose moves toward image -y)
    roll: float = 0.0
    mouth_open: float = 0.0
    left_ear: float = 0.0  # larger = more open
    right_ear: float = 0.0

    @staticmethod
    def none() -> FaceFeatures:
        return FaceFeatures(detected=False)


def _xy(landmarks: np.ndarray, idx: int) -> np.ndarray:
    return np.asarray(landmarks[idx][:2], dtype=np.float64)


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def eye_aspect_ratio(landmarks: np.ndarray, idxs: tuple[int, ...]) -> float:
    p1, p2, p3, p4, p5, p6 = (_xy(landmarks, i) for i in idxs)
    return (_dist(p2, p6) + _dist(p3, p5)) / (2.0 * _dist(p1, p4) + 1e-6)


def mouth_aspect_ratio(landmarks: np.ndarray) -> float:
    upper = _xy(landmarks, MOUTH_UPPER)
    lower = _xy(landmarks, MOUTH_LOWER)
    left = _xy(landmarks, MOUTH_LEFT)
    right = _xy(landmarks, MOUTH_RIGHT)
    return _dist(upper, lower) / (_dist(left, right) + 1e-6)


def extract_features(landmarks: np.ndarray | None) -> FaceFeatures:
    """Convert Face Mesh landmarks (N,2|3) in image coordinates into signals."""
    if landmarks is None:
        return FaceFeatures.none()
    pts = np.asarray(landmarks)
    if pts.ndim != 2 or pts.shape[0] < LANDMARK_COUNT or pts.shape[1] < 2:
        return FaceFeatures.none()

    nose = _xy(pts, NOSE_TIP)
    right_eye = _xy(pts, RIGHT_EYE_OUTER)
    left_eye = _xy(pts, LEFT_EYE_OUTER)
    mid_eye = (left_eye + right_eye) * 0.5
    scale = _dist(left_eye, right_eye) + 1e-6

    # Image x increases right. After the default mirrored webcam, looking to
    # the player's right moves the nose toward +x → +yaw → D.
    yaw = float((nose[0] - mid_eye[0]) / scale)
    # Image y increases down. Looking up moves the nose toward -y → +pitch → W.
    pitch = float((mid_eye[1] - nose[1]) / scale)
    roll = float(np.arctan2(left_eye[1] - right_eye[1], left_eye[0] - right_eye[0]))

    return FaceFeatures(
        detected=True,
        yaw=yaw,
        pitch=pitch,
        roll=roll,
        mouth_open=mouth_aspect_ratio(pts),
        left_ear=eye_aspect_ratio(pts, LEFT_EAR_IDX),
        right_ear=eye_aspect_ratio(pts, RIGHT_EAR_IDX),
    )
