"""Synthetic MovementFrame fixtures for calibration/control development."""

from __future__ import annotations

from collections.abc import Iterator

from tracking.frames import FEATURE_UNITS, MovementFeature, MovementFrame


def synthetic_sequence(name: str, *, start: float = 0.0, step: float = 1.0 / 30.0) -> list[MovementFrame]:
    """Return a named synthetic MovementFrame sequence."""

    builders = {
        "rest": _rest,
        "intentional_movement": _intentional_movement,
        "small_movement": _small_movement,
        "jitter": _jitter,
        "tracking_loss": _tracking_loss,
        "recovery": _recovery,
    }
    if name not in builders:
        raise ValueError(f"unknown synthetic sequence: {name}")
    return list(builders[name](start, step))


def _valid(timestamp: float, mouth: float, turn: float, tilt: float) -> MovementFrame:
    return MovementFrame(
        timestamp_monotonic=timestamp,
        tracking_valid=True,
        features={
            "mouth_opening": MovementFeature.available_value(mouth, FEATURE_UNITS["mouth_opening"]),
            "head_turn": MovementFeature.available_value(turn, FEATURE_UNITS["head_turn"]),
            "head_tilt": MovementFeature.available_value(tilt, FEATURE_UNITS["head_tilt"]),
        },
    )


def _lost(timestamp: float, reason: str = "synthetic_tracking_loss") -> MovementFrame:
    return MovementFrame(
        timestamp_monotonic=timestamp,
        tracking_valid=False,
        features={name: MovementFeature.unavailable(unit, reason) for name, unit in FEATURE_UNITS.items()},
    )


def _rest(start: float, step: float) -> Iterator[MovementFrame]:
    for index in range(30):
        yield _valid(start + index * step, 0.025, 0.0, 0.0)


def _intentional_movement(start: float, step: float) -> Iterator[MovementFrame]:
    values = [0.025, 0.035, 0.055, 0.085, 0.120, 0.150, 0.120, 0.080, 0.040, 0.025]
    for index, mouth in enumerate(values):
        yield _valid(start + index * step, mouth, 0.0, 0.0)


def _small_movement(start: float, step: float) -> Iterator[MovementFrame]:
    values = [0.025, 0.028, 0.031, 0.034, 0.032, 0.029, 0.025]
    for index, mouth in enumerate(values):
        yield _valid(start + index * step, mouth, 0.02, 1.5)


def _jitter(start: float, step: float) -> Iterator[MovementFrame]:
    values = [0.024, 0.027, 0.023, 0.028, 0.025, 0.026, 0.024, 0.027]
    for index, mouth in enumerate(values):
        yield _valid(start + index * step, mouth, (-1) ** index * 0.01, (-1) ** index * 0.8)


def _tracking_loss(start: float, step: float) -> Iterator[MovementFrame]:
    for index in range(5):
        yield _valid(start + index * step, 0.025, 0.0, 0.0)
    for index in range(5, 10):
        yield _lost(start + index * step)


def _recovery(start: float, step: float) -> Iterator[MovementFrame]:
    for index in range(3):
        yield _lost(start + index * step)
    for index in range(3, 10):
        yield _valid(start + index * step, 0.025, 0.0, 0.0)
