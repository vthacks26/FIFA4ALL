"""Live nose-joystick tracking → Quartz OS key holds.

Uses the existing ``control_preview`` mapping (WASD / Space hold / wink L)
and posts HID events the same way ``cursor/face-control-mvp-3874`` did.
Does not import MediaPipe Tasks / FaceLandmarker.
"""

from __future__ import annotations

import argparse
import atexit
import signal
import sys
from time import monotonic

from tracking.control_preview import (
    NoseJoystickState,
    PreviewThresholds,
    _nose_point,
    suggested_keys,
)
from tracking.mac_camera import list_avfoundation_devices, select_builtin_mac_camera
from tracking.mediapipe_tracker import WebcamFaceTracker
from tracking.quartz_keys import HeldKeySession, QuartzKeyInjector, labels_to_keys


def _frontmost_app() -> str:
    if sys.platform != "darwin":
        return ""
    import subprocess

    try:
        out = subprocess.check_output(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ],
            text=True,
            timeout=2,
        )
        return out.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _accessibility_trusted() -> bool | None:
    if sys.platform != "darwin":
        return None
    try:
        import ctypes
        import ctypes.util

        path = ctypes.util.find_library("ApplicationServices") or (
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        lib = ctypes.cdll.LoadLibrary(path)
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        lib.AXIsProcessTrusted.argtypes = []
        return bool(lib.AXIsProcessTrusted())
    except OSError:
        return False


def _apply(session: HeldKeySession, keys: frozenset[str]) -> None:
    prev = session.held()
    session.apply(keys)
    now = session.held()
    for key in sorted(now - prev):
        print(f"KEY down {key}", flush=True)
    for key in sorted(prev - now):
        print(f"KEY up {key}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="MacBook camera → Quartz WASD/Space/L holds for Luna"
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="do not open an OpenCV window (default behavior)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="show the tracking overlay window (steals focus)",
    )
    args = parser.parse_args(argv)
    preview = bool(args.preview) and not bool(args.no_preview)

    devices = list_avfoundation_devices()
    listing = ", ".join(f"{d.index}:{d.name!r}" for d in devices) or "(none)"
    print(f"AVFoundation cameras: {listing}", flush=True)
    try:
        chosen = select_builtin_mac_camera(devices)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        f"Using built-in Mac camera index={chosen.index} name={chosen.name!r} "
        "(refusing iPhone/Continuity)",
        flush=True,
    )

    trusted = _accessibility_trusted()
    if trusted is True:
        print("Accessibility appears granted for this process.", flush=True)
    elif trusted is False:
        print("Accessibility is NOT granted; Quartz keys may be dropped.", file=sys.stderr)

    front = _frontmost_app()
    print(f"Frontmost app: {front or '(unknown)'}", flush=True)
    if front and "Chrome" not in front:
        print(
            "WARNING: Google Chrome is not frontmost. OS keys go to the focused app.",
            file=sys.stderr,
        )

    session = HeldKeySession(QuartzKeyInjector())
    atexit.register(session.release_all)

    def _stop(*_args: object) -> None:
        session.release_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    tracker = WebcamFaceTracker(camera_index=chosen.index, max_width=640)
    try:
        tracker.start()
    except RuntimeError as exc:
        print(f"Could not start webcam tracking: {exc}", file=sys.stderr)
        return 2

    thresholds = PreviewThresholds()
    joystick = NoseJoystickState()
    print(
        "Live Quartz inject. Nose joystick WASD, mouth holds Space, wink holds L. "
        "Ctrl+C quits. Face lost → all keys released.",
        flush=True,
    )
    import cv2  # type: ignore[import-not-found]

    try:
        for tracked in tracker.tracked_frames():
            if tracked.movement.tracking_valid and tracked.landmarks is not None:
                nose = _nose_point(tracked.landmarks)
                offset = joystick.update(nose)
                values = {
                    name: feature.value
                    for name, feature in tracked.movement.features.items()
                    if feature.available and feature.value is not None
                }
                labels = suggested_keys(values, thresholds, offset)
                _apply(session, labels_to_keys(labels))
                print(
                    f"\rtracking=True keys={'+'.join(labels) if labels else '-'}     ",
                    end="",
                    flush=True,
                )
            else:
                joystick.update(None)
                _apply(session, frozenset())
                print("\rtracking=False keys=-     ", end="", flush=True)

            if preview and tracked.image is not None:
                cv2.imshow("tracking live - press q to quit", tracked.image)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    print()
                    break
    finally:
        session.release_all()
        tracker.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
