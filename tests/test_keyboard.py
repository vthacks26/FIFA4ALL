import sys

import pytest

from fifa4all.config import MVP_KEYS
from fifa4all.output.keyboard import (
    HeldKeySession,
    QuartzKeyInjector,
    RecordingKeyInjector,
    create_injector,
)
from fifa4all.replay import FakeClock


def test_recording_press_release_order():
    clock = FakeClock()
    inj = RecordingKeyInjector(clock)
    session = HeldKeySession(inj)
    clock.set(1.0)
    session.apply({"w", "d"})
    clock.set(2.0)
    session.apply({"w"})
    clock.set(3.0)
    session.release_all()
    pairs = [(e.action, e.key) for e in inj.events]
    assert pairs[0:2] == [("down", "d"), ("down", "w")] or set(pairs[0:2]) == {
        ("down", "d"),
        ("down", "w"),
    }
    assert ("up", "d") in pairs
    assert ("up", "w") in pairs
    assert pairs[-1][0] == "up"


def test_hold_duration_preserved():
    clock = FakeClock()
    inj = RecordingKeyInjector(clock)
    session = HeldKeySession(inj)
    clock.set(0.0)
    session.apply({"space"})
    clock.set(0.83)
    session.apply(set())
    down = next(e for e in inj.events if e.action == "down" and e.key == "space")
    up = next(e for e in inj.events if e.action == "up" and e.key == "space")
    assert pytest.approx(up.time_s - down.time_s, rel=0, abs=1e-9) == 0.83


def test_unknown_key_rejected():
    session = HeldKeySession(RecordingKeyInjector())
    with pytest.raises(ValueError):
        session.apply({"enter"})


def test_auto_injector_is_quartz_on_macos_and_not_on_linux():
    inj = create_injector("auto", platform="linux")
    assert inj.__class__.__name__ == "LoggingKeyInjector"
    if sys.platform != "darwin":
        with pytest.raises(RuntimeError, match="macOS"):
            QuartzKeyInjector()
        with pytest.raises(RuntimeError, match="macOS"):
            create_injector("quartz")


def test_mvp_keys_are_wasd_space_l():
    assert MVP_KEYS == ("w", "a", "s", "d", "space", "l")
