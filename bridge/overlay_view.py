"""Look-axis overlay drawn on the game screen.

The orientation website (browser, http://127.0.0.1:8765/) is a separate UI:
onboarding, practice, and live telemetry. This native window is camera/vision
only — the mirrored MacBook frame, face landmarks, WASD look-axis, RESET,
and the Fixed / Follow deadzone switch. Do not draw website chrome
(Welcome, training copy, brand shell) here.

Window behaviour comes from `tracking.overlay`, which makes the OpenCV window a
non-activating panel that floats above a fullscreen Luna without taking focus.
Stealing focus would stop the keys reaching the game, which is the failure this
whole overlay exists to make visible.

The geometry is drawn from the same control state the bridge publishes, so the
overlay, the website, and the keys actually sent can never disagree.
"""

from __future__ import annotations

from typing import Any, Mapping

from tracking.controls import ControlThresholds

LIME = (60, 255, 155)
GREY = (150, 150, 150)
AMBER = (32, 176, 255)
RED = (80, 89, 255)
WHITE = (240, 240, 240)

_KEY_OFFSETS = {"W": (0, -1), "S": (0, 1), "A": (-1, 0), "D": (1, 0)}


def draw_overlay(cv2: Any, frame: Any, state: Mapping[str, object], thresholds: ControlThresholds) -> Any:
    """Draw the look-axis HUD onto a copy of the camera frame."""

    view = frame.copy()
    height, width = view.shape[:2]

    centre = _point(state.get("center_point"), width, height)
    nose = _point(state.get("nose_point"), width, height)
    tracking = bool(state.get("tracking"))

    if centre is not None:
        # Dead zone is elliptical in pixels: normalized units span a wider
        # range horizontally than vertically on a 16:9 frame.
        axes = (
            int(thresholds.exit_radius * width),
            int(thresholds.exit_radius / thresholds.y_scale * height),
        )
        moving = state.get("direction") is not None
        cv2.ellipse(view, centre, axes, 0, 0, 360, GREY if moving else LIME, 2)
        cv2.drawMarker(view, centre, GREY, cv2.MARKER_CROSS, 14, 1)

        keys = state.get("keys")
        held = set(keys) if isinstance(keys, list) else set()
        for label, (dx, dy) in _KEY_OFFSETS.items():
            position = (
                centre[0] + int(dx * axes[0] * 2.1),
                centre[1] + int(dy * axes[1] * 2.1),
            )
            active = label in held
            cv2.circle(view, position, 15, LIME if active else (60, 60, 60), -1 if active else 1)
            cv2.putText(
                view, label, (position[0] - 6, position[1] + 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (20, 20, 20) if active else GREY, 2, cv2.LINE_AA,
            )

    if nose is not None and tracking:
        cv2.circle(view, nose, 9, (255, 255, 255), -1)
        cv2.circle(view, nose, 9, (20, 20, 20), 2)

    _draw_status(cv2, view, state, width, height)
    _draw_reset(cv2, view, width)
    _draw_mode_switch(cv2, view, state, width, height)
    return view


def reset_button_rect(width: int, height: int) -> tuple[int, int, int, int]:
    box_w = min(200, max(120, width // 3))
    box_h = min(56, max(40, height // 7))
    margin = 10
    x2 = max(margin + box_w, width - margin)
    return (x2 - box_w, margin, x2, margin + box_h)


def mode_button_rects(width: int, height: int) -> dict[str, tuple[int, int, int, int]]:
    """FIXED / FOLLOW sit just under RESET in the same look-axis HUD."""

    rx1, _ry1, rx2, ry2 = reset_button_rect(width, height)
    box_h = min(40, max(28, height // 10))
    gap = 6
    y1 = ry2 + gap
    y2 = min(height - 8, y1 + box_h)
    mid = (rx1 + rx2) // 2
    return {
        "fixed": (rx1, y1, mid - 2, y2),
        "follow": (mid + 2, y1, rx2, y2),
    }


def hit_mode_button(x: int, y: int, width: int, height: int) -> str | None:
    """Return `fixed` or `follow` when the click is on that overlay button."""

    for mode, (x1, y1, x2, y2) in mode_button_rects(width, height).items():
        if x1 <= x <= x2 and y1 <= y <= y2:
            return mode
    return None


def apply_overlay_click(source: Any, x: int, y: int, width: int, height: int) -> str | None:
    """Hit-test overlay controls on the same machine that injects WASD.

    Returns ``reset``, ``fixed``, ``follow``, or None.
    """

    x1, y1, x2, y2 = reset_button_rect(width, height)
    if x1 <= x <= x2 and y1 <= y <= y2:
        source.calibrate()
        return "reset"
    mode = hit_mode_button(x, y, width, height)
    if mode is None:
        return None
    source.set_deadzone_mode(mode)
    return mode


def _draw_reset(cv2: Any, view: Any, width: int) -> None:
    height = view.shape[0]
    x1, y1, x2, y2 = reset_button_rect(width, height)
    cv2.rectangle(view, (x1, y1), (x2, y2), (36, 96, 230), -1)
    cv2.rectangle(view, (x1, y1), (x2, y2), WHITE, 2)
    cv2.putText(
        view,
        "RESET",
        (x1 + 18, y1 + (y2 - y1) // 2 + 6),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        WHITE,
        2,
        cv2.LINE_AA,
    )


def _draw_mode_switch(cv2: Any, view: Any, state: Mapping[str, object], width: int, height: int) -> None:
    current = state.get("deadzone_mode")
    if current not in ("fixed", "follow"):
        current = "fixed"
    labels = {"fixed": "FIXED", "follow": "FOLLOW"}
    for mode, (x1, y1, x2, y2) in mode_button_rects(width, height).items():
        active = mode == current
        fill = LIME if active else (60, 60, 60)
        cv2.rectangle(view, (x1, y1), (x2, y2), fill, -1)
        cv2.rectangle(view, (x1, y1), (x2, y2), WHITE if active else GREY, 2)
        label = labels[mode]
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.45
        (tw, th), _ = cv2.getTextSize(label, font, scale, 2)
        tx = x1 + max(4, (x2 - x1 - tw) // 2)
        ty = y1 + (y2 - y1 + th) // 2
        cv2.putText(
            view, label, (tx, ty), font, scale,
            (20, 20, 20) if active else WHITE, 2, cv2.LINE_AA,
        )


def _draw_status(cv2: Any, view: Any, state: Mapping[str, object], width: int, height: int) -> None:
    mouth = state.get("mouth")
    wink = state.get("wink")
    shooting = isinstance(mouth, dict) and bool(mouth.get("active"))
    passing = isinstance(wink, dict) and bool(wink.get("active"))
    armed = bool(state.get("armed"))

    chips = [
        ("ARMED" if armed else "OFF", LIME if armed else GREY),
        ("SHOOT", AMBER if shooting else (70, 70, 70)),
        ("PASS", (250, 180, 140) if passing else (70, 70, 70)),
    ]
    x = 12
    for label, colour in chips:
        cv2.putText(view, label, (x, height - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 2, cv2.LINE_AA)
        x += 90

    if not state.get("tracking"):
        cv2.putText(
            view, "NO FACE", (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, RED, 2, cv2.LINE_AA
        )
    elif armed and state.get("game_focus") is False:
        front = state.get("frontmost") or "another app"
        cv2.putText(
            view, f"FOCUS: {front}", (12, 26),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, AMBER, 2, cv2.LINE_AA,
        )
    else:
        cv2.putText(view, "FIFA4ALL", (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 2, cv2.LINE_AA)


def _point(value: object, width: int, height: int) -> tuple[int, int] | None:
    if not isinstance(value, dict):
        return None
    x, y = value.get("x"), value.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return None
    return (int(x * width), int(y * height))
