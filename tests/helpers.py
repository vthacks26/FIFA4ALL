"""Synthetic MediaPipe-topology faces for tests."""

from __future__ import annotations

import numpy as np


def canonical_landmarks(
    *,
    nose_dx: float = 0.0,
    nose_dy: float = 0.0,
    mouth_open: float = 0.04,
    left_eye_open: float = 0.03,
    right_eye_open: float = 0.03,
) -> np.ndarray:
    """Build 468-point landmarks in normalized image coordinates (y down)."""
    pts = np.zeros((468, 2), dtype=np.float32)
    pts[33] = (0.30, 0.40)
    pts[133] = (0.44, 0.40)
    pts[160] = (0.34, 0.40 - right_eye_open)
    pts[158] = (0.40, 0.40 - right_eye_open)
    pts[153] = (0.40, 0.40 + right_eye_open)
    pts[144] = (0.34, 0.40 + right_eye_open)

    pts[263] = (0.70, 0.40)
    pts[362] = (0.56, 0.40)
    pts[385] = (0.60, 0.40 - left_eye_open)
    pts[387] = (0.66, 0.40 - left_eye_open)
    pts[373] = (0.66, 0.40 + left_eye_open)
    pts[380] = (0.60, 0.40 + left_eye_open)

    pts[1] = (0.50 + nose_dx, 0.48 + nose_dy)
    pts[152] = (0.50, 0.80)

    half_w = 0.08
    pts[13] = (0.50, 0.62)
    pts[14] = (0.50, 0.62 + mouth_open)
    pts[61] = (0.50 - half_w, 0.62 + mouth_open * 0.5)
    pts[291] = (0.50 + half_w, 0.62 + mouth_open * 0.5)
    return pts
