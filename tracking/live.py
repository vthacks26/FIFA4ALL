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
    HoldState,
    NoseJoystickState,
    PreviewThresholds,
    _draw_joystick,
    _draw_landmarks,
    _draw_lines,
    _nose_point,
    suggested_keys,
)
from tracking.mac_camera import list_avfoundation_devices, select_builtin_mac_camera
from tracking.mediapipe_tracker import WebcamFaceTracker
from tracking.overlay import WINDOW_TITLE, decorate_overlay_window, restore_chrome_focus
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


def annotate_frame(
    frame: object,
    *,
    landmarks: object | None,
    joystick: NoseJoystickState,
    thresholds: PreviewThresholds,
    labels: list[str],
    tracking_valid: bool,
    space_hold_seconds: float,
) -> object:
    """Draw face landmarks, WASD nose-joystick zones, and live key labels."""

    import cv2  # type: ignore[import-not-found]

    vis = frame.copy()
    if landmarks is not None:
        _draw_landmarks(cv2, vis, landmarks)
        _draw_joystick(cv2, vis, joystick, landmarks, thresholds)
    charge = min(space_hold_seconds / thresholds.full_space_charge_seconds, 1.0)
    _draw_lines(
        cv2,
        vis,
        [
            f"tracking: {'valid' if tracking_valid else 'lost'}",
            f"keys: {', '.join(labels) if labels else '-'}",
            f"space hold: {space_hold_seconds:.2f}s ({charge * 100:.0f}%)",
        ],
    )
    return vis


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="MacBook camera → Quartz WASD/Space/L holds for Luna"
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="do not open the face / look-axis overlay",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="show face + WASD nose-joystick overlay (non-activating on macOS)",
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
    space_hold = HoldState()
    print(
        "Live Quartz inject. Nose joystick WASD, mouth holds Space, wink holds L. "
        "Ctrl+C quits. Face lost → all keys released.",
        flush=True,
    )
    if preview:
        print(
            f"Face overlay '{WINDOW_TITLE}' is click-through and should stay "
            "above Luna without becoming the key window.",
            flush=True,
        )
    import cv2  # type: ignore[import-not-found]

    overlay_ready = False
    chrome_restored = False
    try:
        for tracked in tracker.tracked_frames():
            labels: list[str] = []
            tracking_valid = bool(
                tracked.movement.tracking_valid and tracked.landmarks is not None
            )
            if tracking_valid:
                nose = _nose_point(tracked.landmarks)
                offset = joystick.update(nose)
                values = {
                    name: feature.value
                    for name, feature in tracked.movement.features.items()
                    if feature.available and feature.value is not None
                }
                labels = suggested_keys(values, thresholds, offset)
                _apply(session, labels_to_keys(labels))
                hold_s = space_hold.update("Space" in labels, monotonic())
            else:
                joystick.update(None)
                _apply(session, frozenset())
                hold_s = space_hold.update(False, monotonic())

            print(
                f"\rtracking={tracking_valid} keys={'+'.join(labels) if labels else '-'}     ",
                end="",
                flush=True,
            )

            if preview and tracked.image is not None:
                vis = annotate_frame(
                    tracked.image,
                    landmarks=tracked.landmarks,
                    joystick=joystick,
                    thresholds=thresholds,
                    labels=labels,
                    tracking_valid=tracking_valid,
                    space_hold_seconds=hold_s,
                )
                cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
                cv2.imshow(WINDOW_TITLE, vis)
                cv2.waitKey(1)
                if not overlay_ready:
                    overlay_ready = decorate_overlay_window(WINDOW_TITLE)
                    if overlay_ready:
                        print("\nOverlay is floating / click-through.", flush=True)
                if not chrome_restored:
                    front_now = _frontmost_app()
                    if front_now and "Chrome" not in front_now:
                        restore_chrome_focus()
                        chrome_restored = True
                        print(f"Frontmost after overlay: {_frontmost_app()}", flush=True)
                    elif front_now and "Chrome" in front_now:
                        chrome_restored = True
    finally:
        session.release_all()
        tracker.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
