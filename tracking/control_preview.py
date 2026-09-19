"""Live tracking-to-key-label preview.

This diagnostic shows what keyboard labels the current tracking values would
suggest, but it never sends keyboard or controller input.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import monotonic

from tracking.mediapipe_tracker import WebcamFaceTracker


@dataclass(frozen=True)
class PreviewThresholds:
    head_turn_left: float = -0.08
    head_turn_right: float = 0.08
    head_tilt_up: float = -8.0
    head_tilt_down: float = 8.0
    mouth_open: float = 0.09
    left_wink: float = 0.025


def suggested_keys(features: dict[str, float], thresholds: PreviewThresholds) -> list[str]:
    """Return keyboard labels for live preview only."""

    keys: list[str] = []
    if features["head_turn"] <= thresholds.head_turn_left:
        keys.append("A")
    if features["head_turn"] >= thresholds.head_turn_right:
        keys.append("D")
    if features["head_tilt"] <= thresholds.head_tilt_up:
        keys.append("W")
    if features["head_tilt"] >= thresholds.head_tilt_down:
        keys.append("S")
    if features["mouth_opening"] >= thresholds.mouth_open:
        keys.append("Space")
    if features["left_wink"] >= thresholds.left_wink:
        keys.append("L")
    return keys


def main() -> int:
    import cv2  # type: ignore[import-not-found]

    thresholds = PreviewThresholds()
    fps_samples: deque[float] = deque(maxlen=30)
    last_time = monotonic()

    print("Live control preview. No keyboard input will be sent. Press q in the preview window to quit.")
    tracker = WebcamFaceTracker(max_width=640)
    try:
        tracker.start()
    except RuntimeError as exc:
        print(f"Could not start webcam tracking: {exc}")
        print("On macOS, grant camera access to the terminal or Codex host, then rerun this command.")
        return 2

    try:
        for tracked in tracker.tracked_frames():
            now = monotonic()
            fps_samples.append(1.0 / max(now - last_time, 1e-6))
            last_time = now

            frame = tracked.image if tracked.image is not None else _blank_frame()
            if tracked.landmarks is not None:
                _draw_landmarks(cv2, frame, tracked.landmarks)

            if tracked.movement.tracking_valid:
                values = {
                    name: feature.value
                    for name, feature in tracked.movement.features.items()
                    if feature.available and feature.value is not None
                }
                keys = suggested_keys(values, thresholds)
            else:
                values = {}
                keys = []

            lines = [
                f"tracking: {'valid' if tracked.movement.tracking_valid else 'lost'}",
                f"preview keys: {', '.join(keys) if keys else '-'}",
                f"rate: {sum(fps_samples) / max(len(fps_samples), 1):.1f} fps",
            ]
            for name in ["head_turn", "head_tilt", "mouth_opening", "left_wink"]:
                value = values.get(name)
                lines.append(f"{name}: {'unavailable' if value is None else f'{value:.3f}'}")

            _draw_lines(cv2, frame, lines)
            print(f"\rtracking={tracked.movement.tracking_valid} keys={'+'.join(keys) if keys else '-'}", end="")
            cv2.imshow("tracking control preview - press q to quit", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                print()
                return 0
        return 0
    finally:
        tracker.stop()


def _blank_frame() -> object:
    import numpy as np

    return np.zeros((360, 640, 3), dtype=np.uint8)


def _draw_landmarks(cv2: object, frame: object, landmarks: list[object]) -> None:
    height, width = frame.shape[:2]
    for index in [1, 13, 14, 33, 145, 159, 234, 263, 374, 386, 454]:
        point = landmarks[index]
        center = (int(point.x * width), int(point.y * height))
        cv2.circle(frame, center, 2, (0, 220, 255), -1)


def _draw_lines(cv2: object, frame: object, lines: list[str]) -> None:
    for index, line in enumerate(lines):
        cv2.putText(
            frame,
            line,
            (20, 32 + index * 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (40, 240, 40),
            2,
            cv2.LINE_AA,
        )


if __name__ == "__main__":
    raise SystemExit(main())
