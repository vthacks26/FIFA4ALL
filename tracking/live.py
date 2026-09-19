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
from tracking.mac_camera import (
    list_avfoundation_devices,
    select_builtin_mac_camera,
    skipped_phone_devices,
)
from tracking.mediapipe_tracker import WebcamFaceTracker
from tracking.overlay import (
    WINDOW_TITLE,
    decorate_overlay_window,
    poll_reset_click,
    restore_chrome_focus,
)
from tracking.quartz_keys import HeldKeySession, QuartzKeyInjector, labels_to_keys

RESET_BUTTON_LABEL = "RESET"


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


def reset_button_rect(width: int, height: int) -> tuple[int, int, int, int]:
    """Top-right Reset hit box in frame pixels (x1, y1, x2, y2)."""

    box_w = min(200, max(120, width // 3))
    box_h = min(56, max(40, height // 7))
    margin = 10
    x2 = max(margin + box_w, width - margin)
    y1 = margin
    return (x2 - box_w, y1, x2, y1 + box_h)


def hit_reset_button(x: int, y: int, width: int, height: int) -> bool:
    x1, y1, x2, y2 = reset_button_rect(width, height)
    return x1 <= x <= x2 and y1 <= y <= y2


def recalibrate_pose(
    joystick: NoseJoystickState,
    space_hold: HoldState,
    session: HeldKeySession,
    extractor: object | None = None,
) -> None:
    """Clear the nose-axis baseline. Next valid face pose is the new neutral."""

    joystick.reset()
    space_hold.started_at = None
    session.release_all()
    reset = getattr(extractor, "reset", None)
    if callable(reset):
        reset()


def _draw_reset_button(cv2: object, vis: object, *, armed: bool) -> None:
    height, width = vis.shape[:2]
    x1, y1, x2, y2 = reset_button_rect(width, height)
    fill = (40, 170, 70) if armed else (36, 96, 230)
    cv2.rectangle(vis, (x1, y1), (x2, y2), fill, -1)
    cv2.rectangle(vis, (x1, y1), (x2, y2), (255, 255, 255), 2)
    label = "SIT STRAIGHT" if armed else RESET_BUTTON_LABEL
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55 if armed else 0.7
    (tw, th), _ = cv2.getTextSize(label, font, scale, 2)
    tx = x1 + max(4, (x2 - x1 - tw) // 2)
    ty = y1 + (y2 - y1 + th) // 2
    cv2.putText(vis, label, (tx, ty), font, scale, (255, 255, 255), 2, cv2.LINE_AA)


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
    camera_name: str | None = None,
    reset_armed: bool = False,
) -> object:
    """Draw face landmarks, WASD nose-joystick zones, live keys, and Reset."""

    import cv2  # type: ignore[import-not-found]

    vis = frame.copy()
    if landmarks is not None:
        _draw_landmarks(cv2, vis, landmarks)
        _draw_joystick(cv2, vis, joystick, landmarks, thresholds)
    charge = min(space_hold_seconds / thresholds.full_space_charge_seconds, 1.0)
    lines = []
    if camera_name:
        lines.append(f"camera: {camera_name}")
    lines.extend(
        [
            f"tracking: {'valid' if tracking_valid else 'lost'}",
            f"keys: {', '.join(labels) if labels else '-'}",
            f"space hold: {space_hold_seconds:.2f}s ({charge * 100:.0f}%)",
            "Reset: sit straight, then tap RESET",
        ]
    )
    _draw_lines(cv2, vis, lines)
    _draw_reset_button(cv2, vis, armed=reset_armed)
    return vis


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="MacBook camera → Quartz WASD/Space/L holds for Luna"
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help=(
            "inject + serve the orientation UI without the overlay or opening a "
            "browser (keeps Luna focused)"
        ),
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help=(
            "show the look-axis overlay and open the orientation intro in your "
            "default browser"
        ),
    )
    parser.add_argument(
        "--ui-port",
        type=int,
        default=8765,
        help="serve the orientation UI on this localhost port",
    )
    args = parser.parse_args(argv)
    preview = bool(args.preview) and not bool(args.no_preview)

    from bridge.server import run_product

    return run_product(preview=preview, port=args.ui_port, mock=False, armed=True)


if __name__ == "__main__":
    raise SystemExit(main())
