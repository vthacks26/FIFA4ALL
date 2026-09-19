"""FIFA4ALL demo runner.

Modes
-----
``--synthetic``  Replay a scripted sequence of head poses / mouth gestures
                 through the full control + keyboard pipeline. Needs no camera,
                 model or display, so it runs anywhere (CI, cloud, laptop).

``--image PATH`` Run Face Mesh on a still image and report the detected head
                 pose and the key it would produce.

``--webcam`` / ``--no-preview``
                 Live capture from the built-in Mac camera only (never iPhone /
                 Continuity Camera). No OpenCV window. Face Mesh 0.10.x, not
                 FaceLandmarker.

The debug output mirrors joe_plan.txt section 9 (HEAD / OUTPUT).
"""

from __future__ import annotations

import argparse
import sys
import time

from .controls.head_direction import DirectionConfig
from .output.keyboard import get_keyboard
from .pipeline import ControlPipeline
from .vision.head_pose import HeadPose


def _print_state(state) -> None:
    keys = " ".join(sorted(state.direction_keys)) or "-"
    action = "  +SPACE" if state.action_fired else ""
    wink = "  +L" if state.wink_held else ""
    print(
        f"HEAD: {state.label:<12} yaw={state.pose.yaw:6.1f} "
        f"pitch={state.pose.pitch:6.1f}  OUTPUT: {keys}{action}{wink}"
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


def _open_builtin_mac_capture():
    import cv2

    from .vision.mac_camera import list_avfoundation_devices, select_builtin_mac_camera

    devices = list_avfoundation_devices()
    listing = ", ".join(f"{d.index}:{d.name!r}" for d in devices) or "(none)"
    print(f"AVFoundation cameras: {listing}", flush=True)
    chosen = select_builtin_mac_camera(devices)
    print(
        f"Using built-in Mac camera index={chosen.index} name={chosen.name!r} "
        "(refusing iPhone/Continuity)",
        flush=True,
    )
    cap = cv2.VideoCapture(chosen.index, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        raise RuntimeError(
            f"could not open built-in Mac camera {chosen.index}:{chosen.name!r}."
        )
    return cap, chosen


def run_image(path: str) -> int:
    """Run the Face Mesh vision stack on a still image."""

    import cv2  # local import: only needed for this mode

    from .vision.face_landmarks import FaceMeshTracker, head_pose_from_features

    bgr = cv2.imread(path)
    if bgr is None:
        print(f"ERROR: could not read image {path!r}", file=sys.stderr)
        return 2

    with FaceMeshTracker() as tracker:
        result = tracker.detect(bgr)

    if not result.detected or result.features is None:
        print("No face detected.")
        return 1

    pose = head_pose_from_features(result.features)
    keyboard = get_keyboard(prefer_real=False)
    pipeline = ControlPipeline(keyboard=keyboard)
    state = pipeline.process(
        pose,
        result.features.mouth_open,
        result.features.left_ear,
        result.features.right_ear,
    )

    print(f"Image: {path}")
    print(f"Landmarks detected: {result.num_landmarks}")
    print(f"mouth_open: {result.features.mouth_open:.3f}")
    _print_state(state)
    return 0


def run_webcam(
    *,
    calibrate_seconds: float = 2.0,
    ready_delay: float = 0.0,
    mirror: bool = True,
) -> int:  # pragma: no cover - needs a camera
    import cv2

    from .vision.face_landmarks import FaceMeshTracker, head_pose_from_features

    try:
        cap, _chosen = _open_builtin_mac_capture()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    keyboard = get_keyboard(prefer_real=True)
    pipeline = ControlPipeline(keyboard=keyboard)
    print("No preview window. Press Ctrl+C to stop.", flush=True)

    tracker = FaceMeshTracker()
    face_lost = False
    try:
        print("Look at the camera with a NEUTRAL face for calibration.", flush=True)
        calib_yaw: list[float] = []
        calib_pitch: list[float] = []
        calib_mouth: list[float] = []
        t0 = time.monotonic()
        while time.monotonic() - t0 < max(0.0, calibrate_seconds):
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            if mirror:
                frame = cv2.flip(frame, 1)
            result = tracker.detect(frame)
            if result.detected and result.features is not None:
                pose = head_pose_from_features(result.features)
                calib_yaw.append(pose.yaw)
                calib_pitch.append(pose.pitch)
                calib_mouth.append(result.features.mouth_open)
        n = float(len(calib_yaw)) or 1.0
        neutral_yaw = sum(calib_yaw) / n if calib_yaw else 0.0
        neutral_pitch = sum(calib_pitch) / n if calib_pitch else 0.0
        neutral_mouth = sum(calib_mouth) / n if calib_mouth else 0.0
        print(
            f"Calibrated yaw={neutral_yaw:+.3f} pitch={neutral_pitch:+.3f} "
            f"mouth={neutral_mouth:.3f}",
            flush=True,
        )
        if ready_delay > 0:
            print(f"Waiting {ready_delay:.1f}s so Chrome can stay focused.", flush=True)
            time.sleep(ready_delay)

        print("Running. Face lost → all keys released.", flush=True)
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                pipeline.keyboard.release_all()
                pipeline.wink.reset()
                continue
            if mirror:
                frame = cv2.flip(frame, 1)
            result = tracker.detect(frame)
            if not result.detected or result.features is None:
                if not face_lost:
                    print("FACE LOST → keys released", flush=True)
                    face_lost = True
                pipeline.keyboard.release_all()
                pipeline.wink.reset()
                pipeline.smoother.reset()
                continue
            face_lost = False
            pose = head_pose_from_features(result.features)
            pose = HeadPose(
                yaw=pose.yaw - neutral_yaw,
                pitch=pose.pitch - neutral_pitch,
                roll=pose.roll,
            )
            mouth = max(0.0, result.features.mouth_open - neutral_mouth)
            state = pipeline.process(
                pose,
                mouth,
                result.features.left_ear,
                result.features.right_ear,
            )
            _print_state(state)
    except KeyboardInterrupt:
        pass
    finally:
        keyboard.release_all()
        cap.release()
        tracker.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FIFA4ALL demo runner")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--synthetic", action="store_true", help="scripted demo")
    group.add_argument("--image", metavar="PATH", help="run on a still image")
    group.add_argument(
        "--webcam",
        action="store_true",
        help="live Mac built-in camera only (never iPhone/Continuity)",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="live Face Mesh on the Mac camera with no OpenCV window",
    )
    parser.add_argument(
        "--calibrate-seconds",
        type=float,
        default=2.0,
        help="neutral-face samples at live start (0 to skip)",
    )
    parser.add_argument(
        "--ready-delay",
        type=float,
        default=0.0,
        help="seconds to wait after calibration before injecting keys",
    )
    args = parser.parse_args(argv)

    if args.image:
        return run_image(args.image)
    if args.webcam or args.no_preview:
        return run_webcam(
            calibrate_seconds=args.calibrate_seconds,
            ready_delay=args.ready_delay,
        )
    return run_synthetic()


if __name__ == "__main__":
    raise SystemExit(main())
