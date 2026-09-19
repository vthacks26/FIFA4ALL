"""Look-axis overlay drawn on the game screen.

The React UI on the second monitor is for the audience. This is for the player:
a small always-on-top window showing the nose-ball and which keys are firing,
so they never have to look away from the match.

Window behaviour comes from `tracking.overlay`, which makes the OpenCV window a
non-activating panel that floats above a fullscreen Luna without taking focus.
Stealing focus would stop the keys reaching the game, which is the failure this
whole overlay exists to make visible.

The geometry is drawn from the same control state the bridge publishes, so the
overlay, the second monitor, and the keys actually sent can never disagree.
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
    return view


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
