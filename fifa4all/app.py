"""FIFA4ALL demo runner.

Modes
-----
``--synthetic``  Replay a scripted sequence of head poses / mouth gestures
                 through the full control + keyboard pipeline. Needs no camera,
                 model or display, so it runs anywhere (CI, cloud, laptop).

``--image PATH`` Run the real MediaPipe FaceLandmarker on a still image and
                 report the detected head pose and the key it would produce.

``--webcam``     Live capture from the default camera. Intended for the local
                 Mac that drives Amazon Luna; not usable on a headless box.

The debug output mirrors joe_plan.txt section 9 (HEAD / OUTPUT).
"""

from __future__ import annotations

import argparse
import sys

from .controls.head_direction import DirectionConfig
from .output.keyboard import get_keyboard
from .pipeline import ControlPipeline
from .vision.head_pose import HeadPose


def _print_state(state) -> None:
    keys = " ".join(sorted(state.direction_keys)) or "-"
    action = "  +SPACE" if state.action_fired else ""
    print(
        f"HEAD: {state.label:<12} yaw={state.pose.yaw:6.1f} "
        f"pitch={state.pose.pitch:6.1f}  OUTPUT: {keys}{action}"
    )


def run_synthetic() -> int:
    """Drive a scripted gesture sequence and print the resulting key events."""

    print("=== FIFA4ALL synthetic control demo (no camera required) ===\n")
    # (yaw, pitch, mouth_open_score, description)
    script = [
        (0.0, 0.0, 0.0, "centered / neutral"),
        (-20.0, 0.0, 0.0, "look left"),
        (0.0, 0.0, 0.0, "back to neutral"),
        (20.0, 0.0, 0.0, "look right"),
        (20.0, -20.0, 0.0, "look up-right (diagonal)"),
        (0.0, 0.0, 0.9, "mouth O -> action"),
        (0.0, 0.0, 0.9, "mouth still open (must NOT re-fire)"),
        (0.0, 0.0, 0.0, "mouth closed -> re-arm"),
        (0.0, 25.0, 0.8, "look down + mouth O"),
        (0.0, 0.0, 0.0, "neutral (release everything)"),
    ]

    keyboard = get_keyboard(prefer_real=False)
    pipeline = ControlPipeline(
        keyboard=keyboard,
        direction_config=DirectionConfig(yaw_threshold=8.0, pitch_threshold=8.0),
    )

    for yaw, pitch, mouth, desc in script:
        print(f"\n-- {desc}")
        # Feed each pose a few times so the EMA smoother settles.
        for _ in range(6):
            state = pipeline.process(HeadPose(yaw, pitch, 0.0), mouth)
        _print_state(state)

    keyboard.release_all()
    print(f"\nTotal keyboard events emitted: {len(keyboard.backend.events)}")
    return 0


def run_image(path: str) -> int:
    """Run the real vision stack on a still image."""

    import cv2  # local import: only needed for this mode

    from .vision.face_landmarks import FaceLandmarkerWrapper
    from .vision.head_pose import head_pose_from_matrix

    bgr = cv2.imread(path)
    if bgr is None:
        print(f"ERROR: could not read image {path!r}", file=sys.stderr)
        return 2

    with FaceLandmarkerWrapper() as landmarker:
        result = landmarker.detect(bgr)

    if not result.detected:
        print("No face detected.")
        return 1

    pose = head_pose_from_matrix(result.transform_matrix)
    keyboard = get_keyboard(prefer_real=False)
    pipeline = ControlPipeline(keyboard=keyboard)
    state = pipeline.process(pose, result.blendshape("jawOpen"))

    print(f"Image: {path}")
    print(f"Landmarks detected: {result.num_landmarks}")
    print(f"jawOpen blendshape: {result.blendshape('jawOpen'):.3f}")
    _print_state(state)
    return 0


def run_webcam() -> int:  # pragma: no cover - needs a camera + display
    import cv2

    from .vision.face_landmarks import FaceLandmarkerWrapper
    from .vision.head_pose import head_pose_from_matrix

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: could not open webcam (device 0).", file=sys.stderr)
        return 2

    keyboard = get_keyboard(prefer_real=True)
    pipeline = ControlPipeline(keyboard=keyboard)
    print("Press Ctrl+C to stop.")
    try:
        with FaceLandmarkerWrapper() as landmarker:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                result = landmarker.detect(frame)
                if result.detected:
                    pose = head_pose_from_matrix(result.transform_matrix)
                    state = pipeline.process(pose, result.blendshape("jawOpen"))
                    _print_state(state)
    except KeyboardInterrupt:
        pass
    finally:
        keyboard.release_all()
        cap.release()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FIFA4ALL demo runner")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--synthetic", action="store_true", help="scripted demo")
    group.add_argument("--image", metavar="PATH", help="run on a still image")
    group.add_argument("--webcam", action="store_true", help="live camera (local)")
    args = parser.parse_args(argv)

    if args.image:
        return run_image(args.image)
    if args.webcam:
        return run_webcam()
    return run_synthetic()


if __name__ == "__main__":
    raise SystemExit(main())
