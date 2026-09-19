import pytest

from fifa4all.config import make_test_config
from fifa4all.output.keyboard import RecordingKeyInjector
from fifa4all.replay import FakeClock, hold_duration, run_feature_frames


def _open_eyes():
    return {"left_ear": 0.30, "right_ear": 0.30, "mouth_open": 0.10}


def test_pipeline_shot_hold_duration():
    dt = 0.05
    frames = [{**_open_eyes(), "yaw": 0.0, "pitch": 0.0}] * 5
    frames += [{**_open_eyes(), "mouth_open": 0.55, "yaw": 0.0, "pitch": 0.0}] * 20
    frames += [{**_open_eyes(), "yaw": 0.0, "pitch": 0.0}] * 5
    clock = FakeClock()
    inj = RecordingKeyInjector(clock)
    run_feature_frames(frames, inj, config=make_test_config(), dt_sec=dt, clock=clock)
    duration = hold_duration(inj.events, "space")
    assert duration == pytest.approx(20 * dt, abs=1e-9)


def test_pipeline_wink_pass_hold_duration():
    dt = 0.05
    frames = [{**_open_eyes()}] * 3
    frames += [{"mouth_open": 0.10, "left_ear": 0.08, "right_ear": 0.30}] * 10
    frames += [{**_open_eyes()}] * 3
    clock = FakeClock()
    inj = RecordingKeyInjector(clock)
    run_feature_frames(frames, inj, config=make_test_config(), dt_sec=dt, clock=clock)
    assert hold_duration(inj.events, "l") == pytest.approx(10 * dt, abs=1e-9)
    assert hold_duration(inj.events, "space") is None


def test_pipeline_diagonal_and_shoot_together():
    frames = [
        {"yaw": 0.4, "pitch": 0.4, "mouth_open": 0.55, "left_ear": 0.3, "right_ear": 0.3}
    ]
    clock = FakeClock()
    inj = RecordingKeyInjector(clock)
    intents = run_feature_frames(frames, inj, config=make_test_config(), dt_sec=0.05, clock=clock)
    assert intents[0].held_keys() == frozenset({"w", "d", "space"})
    keys_down = {e.key for e in inj.events if e.action == "down"}
    assert keys_down == {"w", "d", "space"}


def test_pipeline_face_lost_releases():
    frames = [
        {"yaw": 0.4, "mouth_open": 0.55, "left_ear": 0.08, "right_ear": 0.3},
        {"detected": False},
    ]
    clock = FakeClock()
    inj = RecordingKeyInjector(clock)
    intents = run_feature_frames(frames, inj, config=make_test_config(), dt_sec=0.05, clock=clock)
    assert "d" in intents[0].held_keys()
    assert intents[1].held_keys() == frozenset()
    ups = [e.key for e in inj.events if e.action == "up"]
    downs = [e.key for e in inj.events if e.action == "down"]
    assert set(downs) <= set(ups)


def test_blink_does_not_pass():
    frames = [{"mouth_open": 0.1, "left_ear": 0.08, "right_ear": 0.08}] * 8
    clock = FakeClock()
    inj = RecordingKeyInjector(clock)
    run_feature_frames(frames, inj, config=make_test_config(), dt_sec=0.05, clock=clock)
    assert all(e.key != "l" for e in inj.events)
