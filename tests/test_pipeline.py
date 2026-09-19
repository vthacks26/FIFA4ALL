from fifa4all.controls.head_direction import DirectionConfig
from fifa4all.output.keyboard import KeyboardController, LoggingBackend
from fifa4all.pipeline import ControlPipeline
from fifa4all.vision.head_pose import HeadPose, PoseSmoother


def make_pipeline():
    backend = LoggingBackend()
    kb = KeyboardController(backend)
    pipeline = ControlPipeline(
        keyboard=kb,
        direction_config=DirectionConfig(yaw_threshold=8.0, pitch_threshold=8.0),
        smoother=PoseSmoother(alpha=1.0),  # no smoothing lag for deterministic test
    )
    return pipeline, backend


def test_head_turn_presses_then_releases():
    pipeline, backend = make_pipeline()

    state = pipeline.process(HeadPose(yaw=25.0, pitch=0.0, roll=0.0), 0.0)
    assert state.direction_keys == frozenset({"D"})
    assert state.label == "RIGHT"

    pipeline.process(HeadPose(yaw=0.0, pitch=0.0, roll=0.0), 0.0)
    presses = [e for e in backend.events if e.action == "press"]
    releases = [e for e in backend.events if e.action == "release"]
    assert presses[0].key == "D"
    assert releases[0].key == "D"


def test_mouth_open_taps_space_once():
    pipeline, backend = make_pipeline()
    pipeline.process(HeadPose(0, 0, 0), 0.9)   # opens -> tap
    pipeline.process(HeadPose(0, 0, 0), 0.9)   # still open -> no tap
    taps = [e for e in backend.events if e.action == "tap"]
    assert len(taps) == 1
    assert taps[0].key == "SPACE"


def test_wink_holds_l_then_releases():
    pipeline, backend = make_pipeline()
    state = pipeline.process(HeadPose(0, 0, 0), 0.0, left_ear=0.10, right_ear=0.30)
    assert state.wink_held is True
    assert pipeline.keyboard.held == frozenset({"L"})
    pipeline.process(HeadPose(0, 0, 0), 0.0, left_ear=0.30, right_ear=0.30)
    assert pipeline.keyboard.held == frozenset()
    presses = [e for e in backend.events if e.action == "press"]
    releases = [e for e in backend.events if e.action == "release"]
    assert presses[0].key == "L"
    assert releases[0].key == "L"


def test_diagonal_label():
    pipeline, _ = make_pipeline()
    state = pipeline.process(HeadPose(yaw=25.0, pitch=-25.0, roll=0.0), 0.0)
    assert state.direction_keys == frozenset({"D", "W"})
    assert state.label == "UP+RIGHT"
