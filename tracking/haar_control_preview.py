"""Lightweight OpenCV-only live control-label preview.

This is a fallback diagnostic for Macs where MediaPipe Tasks are unavailable.
It never sends keyboard input; it only shows suggested labels.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from time import monotonic


@dataclass
class NeutralFace:
    center_x: float
    center_y: float
    width: float
    height: float


def main() -> int:
    import cv2  # type: ignore[import-not-found]
    import numpy as np

    cascade_path = Path("models/haarcascade_frontalface_default.xml")
    if not cascade_path.exists():
        print(f"Missing {cascade_path}. Download the OpenCV frontal-face cascade first.")
        return 2

    face_cascade = cv2.CascadeClassifier(str(cascade_path))
    capture = cv2.VideoCapture(0)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not capture.isOpened():
        print("Could not open camera index 0. Check macOS camera permission for the terminal/Codex host.")
        return 2

    neutral: NeutralFace | None = None
    fps_samples: deque[float] = deque(maxlen=30)
    last_time = monotonic()
    print("OpenCV fallback preview. No keyboard input will be sent. Press q to quit; press r to reset neutral.")

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                print("\nCamera read failed.")
                return 2

            frame = _resize(cv2, frame, 640)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
            now = monotonic()
            fps_samples.append(1.0 / max(now - last_time, 1e-6))
            last_time = now

            keys: list[str] = []
            metrics = ["tracking: lost"]
            if len(faces):
                x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
                cx = x + w / 2.0
                cy = y + h / 2.0
                if neutral is None:
                    neutral = NeutralFace(cx, cy, w, h)

                dx = (cx - neutral.center_x) / max(neutral.width, 1.0)
                dy = (cy - neutral.center_y) / max(neutral.height, 1.0)
                mouth_score = _mouth_dark_score(gray[y : y + h, x : x + w], np)

                if dx <= -0.18:
                    keys.append("A")
                if dx >= 0.18:
                    keys.append("D")
                if dy <= -0.16:
                    keys.append("W")
                if dy >= 0.16:
                    keys.append("S")
                if mouth_score >= 0.18:
                    keys.append("Space")

                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 220, 255), 2)
                metrics = [
                    "tracking: valid",
                    f"head_dx: {dx:.3f}",
                    f"head_dy: {dy:.3f}",
                    f"mouth_score: {mouth_score:.3f}",
                    "wink: unavailable in fallback",
                ]

            lines = [
                f"preview keys: {', '.join(keys) if keys else '-'}",
                f"rate: {sum(fps_samples) / max(len(fps_samples), 1):.1f} fps",
                *metrics,
            ]
            _draw_lines(cv2, frame, lines)
            print(f"\rkeys={'+'.join(keys) if keys else '-'} {metrics[0]}", end="")

            cv2.imshow("OpenCV fallback control preview - q quit, r reset", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                print()
                return 0
            if key == ord("r"):
                neutral = None
    finally:
        capture.release()
        cv2.destroyAllWindows()


def _resize(cv2: object, frame: object, max_width: int) -> object:
    height, width = frame.shape[:2]
    if width <= max_width:
        return frame
    scale = max_width / width
    return cv2.resize(frame, (max_width, int(height * scale)))


def _mouth_dark_score(face_gray: object, np: object) -> float:
    height, width = face_gray.shape[:2]
    lower = face_gray[int(height * 0.58) : int(height * 0.88), int(width * 0.25) : int(width * 0.75)]
    if lower.size == 0:
        return 0.0
    threshold = max(30.0, float(np.mean(lower) - np.std(lower)))
    return float(np.mean(lower < threshold))


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
