"""Standalone webcam diagnostic for tracking measurements."""

from __future__ import annotations

from collections import deque
from time import monotonic

from tracking.mediapipe_tracker import WebcamFaceTracker


def main() -> int:
    import cv2  # type: ignore[import-not-found]

    fps_samples: deque[float] = deque(maxlen=30)
    last_time = monotonic()
    with WebcamFaceTracker() as tracker:
        for frame, movement in tracker.frames():
            now = monotonic()
            fps_samples.append(1.0 / max(now - last_time, 1e-6))
            last_time = now

            if frame is None:
                frame = _blank_frame(cv2)
            lines = [
                f"tracking: {'valid' if movement.tracking_valid else 'lost'}",
                f"rate: {sum(fps_samples) / max(len(fps_samples), 1):.1f} fps",
            ]
            for name, feature in movement.features.items():
                value = "unavailable" if not feature.available else f"{feature.value:.3f} {feature.unit}"
                lines.append(f"{name}: {value}")

            _draw_lines(cv2, frame, lines)
            cv2.imshow("tracking diagnostic - press q to quit", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                return 0
    return 0


def _blank_frame(cv2: object) -> object:
    import numpy as np

    return np.zeros((360, 640, 3), dtype=np.uint8)


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
