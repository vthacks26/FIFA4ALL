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
    joystick_deadzone_x: float = 0.045
    joystick_deadzone_y: float = 0.040
    mouth_open: float = 0.09
    left_wink: float = 0.025
    full_space_charge_seconds: float = 1.25


@dataclass
class HoldState:
    started_at: float | None = None

    def update(self, active: bool, now: float) -> float:
        if not active:
            self.started_at = None
            return 0.0
        if self.started_at is None:
            self.started_at = now
        return now - self.started_at


@dataclass
class NoseJoystickState:
    center: tuple[float, float] | None = None

    def update(self, nose: tuple[float, float] | None) -> tuple[float, float]:
        if nose is None:
            return (0.0, 0.0)
        if self.center is None:
            self.center = nose
        return (nose[0] - self.center[0], nose[1] - self.center[1])

    def reset(self) -> None:
        self.center = None


def suggested_keys(
    features: dict[str, float],
    thresholds: PreviewThresholds,
    joystick_offset: tuple[float, float],
) -> list[str]:
    """Return keyboard labels for live preview only."""

    keys: list[str] = []
    if joystick_offset[0] <= -thresholds.joystick_deadzone_x:
        keys.append("D")
    if joystick_offset[0] >= thresholds.joystick_deadzone_x:
        keys.append("A")
    if joystick_offset[1] <= -thresholds.joystick_deadzone_y:
        keys.append("W")
    if joystick_offset[1] >= thresholds.joystick_deadzone_y:
        keys.append("S")
    if features["mouth_opening"] >= thresholds.mouth_open:
        keys.append("Space")
    if features["left_wink"] >= thresholds.left_wink:
        keys.append("L")
    return keys


def main() -> int:
    import cv2  # type: ignore[import-not-found]

    thresholds = PreviewThresholds()
    space_hold = HoldState()
    joystick = NoseJoystickState()
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
                _draw_joystick(cv2, frame, joystick, tracked.landmarks, thresholds)

            if tracked.movement.tracking_valid:
                nose = _nose_point(tracked.landmarks)
                joystick_offset = joystick.update(nose)
                values = {
                    name: feature.value
                    for name, feature in tracked.movement.features.items()
                    if feature.available and feature.value is not None
                }
                keys = suggested_keys(values, thresholds, joystick_offset)
                space_hold_seconds = space_hold.update("Space" in keys, now)
            else:
                values = {}
                joystick_offset = joystick.update(None)
                keys = []
                space_hold_seconds = space_hold.update(False, now)

            space_charge = min(space_hold_seconds / thresholds.full_space_charge_seconds, 1.0)

            lines = [
                f"tracking: {'valid' if tracked.movement.tracking_valid else 'lost'}",
                f"preview keys: {', '.join(keys) if keys else '-'}",
                f"nose joystick: x={joystick_offset[0]:.3f} y={joystick_offset[1]:.3f}",
                f"space hold: {space_hold_seconds:.2f}s ({space_charge * 100:.0f}%)",
                f"rate: {sum(fps_samples) / max(len(fps_samples), 1):.1f} fps",
            ]
            for name in ["head_turn", "head_tilt", "mouth_opening", "left_wink"]:
                value = values.get(name)
                lines.append(f"{name}: {'unavailable' if value is None else f'{value:.3f}'}")

            _draw_lines(cv2, frame, lines)
            print(
                f"\rtracking={tracked.movement.tracking_valid} "
                f"keys={'+'.join(keys) if keys else '-'} "
                f"space_hold={space_hold_seconds:.2f}s",
                end="",
            )
            cv2.imshow("tracking control preview - press q to quit", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                print()
                return 0
            if key == ord("r"):
                joystick.reset()
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


def _nose_point(landmarks: list[object] | None) -> tuple[float, float] | None:
    if landmarks is None:
        return None
    nose = landmarks[1]
    return (float(nose.x), float(nose.y))


def _draw_joystick(
    cv2: object,
    frame: object,
    joystick: NoseJoystickState,
    landmarks: list[object],
    thresholds: PreviewThresholds,
) -> None:
    height, width = frame.shape[:2]
    nose = _nose_point(landmarks)
    if nose is None or joystick.center is None:
        return

    # 1. Setup coordinates
    nose_px = (int(nose[0] * width), int(nose[1] * height))
    center_px = (int(joystick.center[0] * width), int(joystick.center[1] * height))
    
    # Calculate the boundary lines based on your thresholds
    dx = int(thresholds.joystick_deadzone_x * width)
    dy = int(thresholds.joystick_deadzone_y * height)

    # Zone Boundaries (Lines that separate the areas)
    left_line = center_px[0] - dx
    right_line = center_px[0] + dx
    top_line = center_px[1] - dy
    bottom_line = center_px[1] + dy

    grid_color = (255, 120, 40)  # Orange
    active_color = (0, 255, 0)   # Green for the nose
    font = cv2.FONT_HERSHEY_SIMPLEX

    # 2. DRAW THE GRID (Creating the "Areas")
    # Vertical boundary lines
    cv2.line(frame, (left_line, 0), (left_line, height), grid_color, 1)
    cv2.line(frame, (right_line, 0), (right_line, height), grid_color, 1)
    # Horizontal boundary lines
    cv2.line(frame, (0, top_line), (width, top_line), grid_color, 1)
    cv2.line(frame, (0, bottom_line), (width, bottom_line), grid_color, 1)

    # 3. LABEL THE AREAS (So you know exactly where to put your nose)
    # The current logic in suggested_keys: A is Right, D is Left, W is Up, S is Down
    
    # Corners (Diagonal Areas)
    cv2.putText(frame, "WD", (20, 40), font, 0.8, grid_color, 2)            # Top-Left
    cv2.putText(frame, "WA", (width - 70, 40), font, 0.8, grid_color, 2)   # Top-Right
    cv2.putText(frame, "DS", (20, height - 20), font, 0.8, grid_color, 2)  # Bottom-Left
    cv2.putText(frame, "AS", (width - 70, height - 20), font, 0.8, grid_color, 2) # Bottom-Right

    # Cardinal Areas
    cv2.putText(frame, "W", (center_px[0] - 10, 40), font, 0.8, grid_color, 2)
    cv2.putText(frame, "S", (center_px[0] - 10, height - 20), font, 0.8, grid_color, 2)
    cv2.putText(frame, "D", (20, center_px[1] + 10), font, 0.8, grid_color, 2)
    cv2.putText(frame, "A", (width - 40, center_px[1] + 10), font, 0.8, grid_color, 2)

    # Neutral Center
    cv2.putText(frame, "Neutral", (center_px[0] - 30, center_px[1] + 5), font, 0.5, grid_color, 1)

    # 4. DRAW THE NOSE TRACKER
    # Draw a circle for the nose so the user can see which box they are in
    cv2.circle(frame, nose_px, 8, active_color, -1)
    
    # Optional: Draw a small line from center to nose to show direction
    cv2.line(frame, center_px, nose_px, active_color, 2)

    
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
