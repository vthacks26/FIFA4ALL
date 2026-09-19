"""Lightweight OpenCV-only nose control-label preview.

This is a fallback diagnostic for Macs where MediaPipe Tasks are unavailable.
It never sends keyboard input; it only shows suggested labels.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from time import monotonic


@dataclass
class NeutralNose:
    rel_x: float
    rel_y: float


def main() -> int:
    import cv2  # type: ignore[import-not-found]
    cascade_path = Path("models/haarcascade_frontalface_default.xml")
    nose_cascade_path = Path("models/haarcascade_mcs_nose.xml")
    if not cascade_path.exists() or not nose_cascade_path.exists():
        print("Missing OpenCV cascade files in models/.")
        return 2

    face_cascade = cv2.CascadeClassifier(str(cascade_path))
    nose_cascade = cv2.CascadeClassifier(str(nose_cascade_path))
    # Not cv2.VideoCapture: OpenCV's macOS backend races on the pixel buffer and
    # segfaults. See tracking/avf_camera.py.
    from tracking.avf_camera import AVFCamera, CameraError, CameraNotStarted
    from tracking.mac_camera import resolve_mac_camera

    chosen = resolve_mac_camera()
    capture = AVFCamera(unique_id=chosen.unique_id, name=chosen.name)
    capture.start()
    if not capture.is_open:
        capture.stop()  # never leave a half-open session behind
        print(f"Could not open camera {chosen.name!r}. Check macOS camera permission for the terminal/Codex host.")
        return 2

    neutral: NeutralNose | None = None
    fps_samples: deque[float] = deque(maxlen=30)
    last_time = monotonic()
    print("Nose tracking preview. No keyboard input will be sent. Press q to quit; press r to reset neutral.")

    try:
        while True:
            try:
                ok, frame = capture.read()
            except CameraNotStarted:
                print("\nCamera stopped.")
                return 2
            except CameraError as exc:
                # A single bad frame is not fatal to a preview; keep going.
                print(f"\n{exc}")
                continue
            if not ok:
                # A read timeout means no frame arrived in time, not that the
                # camera died. Retry rather than ending the preview.
                continue

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
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 220, 255), 2)
                nose = _detect_nose(nose_cascade, gray[y : y + h, x : x + w])
                if nose is not None:
                    nx, ny, nw, nh = nose
                    nose_cx = x + nx + nw / 2.0
                    nose_cy = y + ny + nh / 2.0
                    rel_x = (nose_cx - x) / max(w, 1.0)
                    rel_y = (nose_cy - y) / max(h, 1.0)
                    if neutral is None:
                        neutral = NeutralNose(rel_x, rel_y)

                    dx = rel_x - neutral.rel_x
                    dy = rel_y - neutral.rel_y

                    if dx <= -0.055:
                        keys.append("A")
                    if dx >= 0.055:
                        keys.append("D")
                    if dy <= -0.040:
                        keys.append("W")
                    if dy >= 0.035:
                        keys.append("S")

                    cv2.rectangle(frame, (x + nx, y + ny), (x + nx + nw, y + ny + nh), (255, 120, 40), 2)
                    cv2.circle(frame, (int(nose_cx), int(nose_cy)), 4, (0, 255, 0), -1)
                    metrics = [
                        "tracking: valid",
                        f"nose_dx: {dx:.3f}",
                        f"nose_dy: {dy:.3f}",
                        "forward: no key",
                    ]
                else:
                    metrics = ["tracking: face_valid_nose_lost"]

            lines = [
                f"preview keys: {', '.join(keys) if keys else '-'}",
                f"rate: {sum(fps_samples) / max(len(fps_samples), 1):.1f} fps",
                *metrics,
            ]
            _draw_lines(cv2, frame, lines)
            print(f"\rkeys={'+'.join(keys) if keys else '-'} {metrics[0]}", end="")

            cv2.imshow("Nose control preview - q quit, r reset", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                print()
                return 0
            if key == ord("r"):
                neutral = None
    finally:
        capture.stop()
        cv2.destroyAllWindows()


def _resize(cv2: object, frame: object, max_width: int) -> object:
    height, width = frame.shape[:2]
    if width <= max_width:
        return frame
    scale = max_width / width
    return cv2.resize(frame, (max_width, int(height * scale)))


def _detect_nose(nose_cascade: object, face_gray: object) -> tuple[int, int, int, int] | None:
    height, width = face_gray.shape[:2]
    search = face_gray[int(height * 0.25) : int(height * 0.78), int(width * 0.20) : int(width * 0.80)]
    noses = nose_cascade.detectMultiScale(search, scaleFactor=1.15, minNeighbors=4, minSize=(24, 24))
    if len(noses) == 0:
        return None
    nx, ny, nw, nh = max(noses, key=lambda box: box[2] * box[3])
    return (int(nx + width * 0.20), int(ny + height * 0.25), int(nw), int(nh))


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
