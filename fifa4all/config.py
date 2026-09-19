"""Tunable detection thresholds. Gesture *mappings* are locked for the MVP."""

from __future__ import annotations

from dataclasses import dataclass


# Locked EA FC (Amazon Luna / Chrome / US keyboard) bindings.
KEY_FORWARD = "w"
KEY_LEFT = "a"
KEY_BACK = "s"
KEY_RIGHT = "d"
KEY_SHOOT = "space"
KEY_PASS = "l"

MVP_KEYS = (KEY_FORWARD, KEY_LEFT, KEY_BACK, KEY_RIGHT, KEY_SHOOT, KEY_PASS)


@dataclass(frozen=True)
class Config:
    """Feature → intent thresholds. Not a customizable-gesture system."""

    ema_alpha: float = 0.4
    yaw_enter: float = 0.18
    yaw_exit: float = 0.10
    pitch_enter: float = 0.16
    pitch_exit: float = 0.09
    mouth_open: float = 0.35
    mouth_close: float = 0.22
    wink_closed: float = 0.16
    wink_open: float = 0.22
    calibrate_seconds: float = 2.0
    ready_delay_seconds: float = 5.0
    camera_index: int = 0
    mirror: bool = True
    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.5


def make_test_config() -> Config:
    """Deterministic config for unit tests (no smoothing, known thresholds)."""
    return Config(
        ema_alpha=1.0,
        yaw_enter=0.18,
        yaw_exit=0.10,
        pitch_enter=0.16,
        pitch_exit=0.09,
        mouth_open=0.35,
        mouth_close=0.22,
        wink_closed=0.16,
        wink_open=0.22,
        calibrate_seconds=0.0,
        ready_delay_seconds=0.0,
    )
