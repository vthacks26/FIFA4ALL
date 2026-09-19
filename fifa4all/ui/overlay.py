"""Debug overlay drawn on the camera frame."""

from __future__ import annotations

from typing import Any

from fifa4all.controls.intent import ControlIntent, GestureEngine
from fifa4all.vision.features import FaceFeatures


def draw_overlay(
    frame_bgr: Any,
    features: FaceFeatures,
    intent: ControlIntent,
    engine: GestureEngine,
    *,
    status: str = "",
) -> Any:
    import cv2
    import numpy as np

    out = frame_bgr.copy()
    h, w = out.shape[:2]
    panel_w = min(420, w)
    overlay = out.copy()
    cv2.rectangle(overlay, (0, 0), (panel_w, 250), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.65, out, 0.35, 0, out)

    keys = intent.keys_label()
    head = intent.head_label()
    mouth = "OPEN" if intent.hold_space else "closed"
    wink = "YES" if intent.hold_l else "no"
    face = "YES" if features.detected else "NO"
    cal = "YES" if engine.calibrated else "NO"

    lines = [
        "FIFA4ALL  face control",
        f"FACE {face}   CAL {cal}",
        f"HEAD  {head}",
        f"MOUTH {mouth}    WINK {wink}",
        f"KEYS  {keys}",
        f"yaw {engine.yaw_smoothed:+.2f}  pitch {engine.pitch_smoothed:+.2f}",
        f"MAR {features.mouth_open:.2f}  L/R EAR {features.left_ear:.2f}/{features.right_ear:.2f}",
    ]
    if status:
        lines.append(status)

    y = 28
    for i, text in enumerate(lines):
        color = (220, 220, 220)
        if i == 0:
            color = (80, 220, 120)
        if i == 4 and intent.held_keys():
            color = (80, 200, 255)
        cv2.putText(
            out,
            text,
            (16, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62 if i else 0.72,
            color,
            2,
            cv2.LINE_AA,
        )
        y += 30

    if features.detected:
        # Direction cue from image center.
        cx, cy = w // 2, h // 2
        dx = int(np.clip(engine.yaw_smoothed, -1, 1) * 120)
        dy = int(np.clip(-engine.pitch_smoothed, -1, 1) * 120)
        cv2.arrowedLine(out, (cx, cy), (cx + dx, cy + dy), (80, 220, 120), 3, tipLength=0.2)

    return out
