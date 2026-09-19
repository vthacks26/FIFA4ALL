"""Headless replay of feature frames → held-key events."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from fifa4all.config import Config, make_test_config
from fifa4all.controls.intent import ControlIntent, GestureEngine
from fifa4all.output.keyboard import HeldKeySession, KeyEvent, KeyInjector, RecordingKeyInjector
from fifa4all.vision.features import FaceFeatures


def features_from_dict(row: dict[str, Any]) -> FaceFeatures:
    if not row.get("detected", True):
        return FaceFeatures.none()
    return FaceFeatures(
        detected=True,
        yaw=float(row.get("yaw", 0.0)),
        pitch=float(row.get("pitch", 0.0)),
        roll=float(row.get("roll", 0.0)),
        mouth_open=float(row.get("mouth_open", row.get("mouth", 0.0))),
        left_ear=float(row.get("left_ear", 0.28)),
        right_ear=float(row.get("right_ear", 0.28)),
    )


def load_replay(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


_CONFIG_OVERRIDE_KEYS = (
    "ema_alpha",
    "yaw_enter",
    "yaw_exit",
    "pitch_enter",
    "pitch_exit",
    "mouth_open",
    "mouth_close",
    "wink_closed",
    "wink_open",
)


def config_with_payload(config: Config, payload: dict[str, Any]) -> Config:
    updates = {k: payload[k] for k in _CONFIG_OVERRIDE_KEYS if k in payload}
    return replace(config, **updates) if updates else config


class FakeClock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def set(self, t: float) -> None:
        self.t = t

    def step(self, dt: float) -> None:
        self.t += dt


def run_feature_frames(
    frames: Iterable[dict[str, Any] | FaceFeatures],
    injector: KeyInjector,
    *,
    config: Config | None = None,
    dt_sec: float = 1.0 / 30.0,
    clock: FakeClock | None = None,
    calibrate_first: int = 0,
) -> list[ControlIntent]:
    engine = GestureEngine(config or make_test_config())
    session = HeldKeySession(injector)
    clock = clock or FakeClock()
    if isinstance(injector, RecordingKeyInjector):
        injector._clock = clock
    intents: list[ControlIntent] = []
    rows = list(frames)

    if calibrate_first:
        for row in rows[:calibrate_first]:
            feat = row if isinstance(row, FaceFeatures) else features_from_dict(row)
            engine.add_calibration_sample(feat)
        engine.finish_calibration()

    try:
        for i, row in enumerate(rows):
            clock.set(i * dt_sec)
            feat = row if isinstance(row, FaceFeatures) else features_from_dict(row)
            if not engine.calibrated and calibrate_first == 0:
                engine.calibrated = True
            intent = engine.update(feat)
            session.apply(intent.held_keys())
            intents.append(intent)
    finally:
        clock.set(len(rows) * dt_sec)
        session.release_all()
    return intents


def hold_duration(events: list[KeyEvent], key: str) -> float | None:
    down = next((e.time_s for e in events if e.key == key and e.action == "down"), None)
    up = next((e.time_s for e in events if e.key == key and e.action == "up"), None)
    if down is None or up is None:
        return None
    return up - down
