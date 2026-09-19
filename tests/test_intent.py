from fifa4all.config import make_test_config
from fifa4all.controls.intent import GestureEngine
from fifa4all.vision.features import FaceFeatures, extract_features
from tests.helpers import canonical_landmarks


def _engine() -> GestureEngine:
    eng = GestureEngine(make_test_config())
    eng.calibrated = True
    return eng


def _face(**kwargs) -> FaceFeatures:
    return FaceFeatures(detected=True, **kwargs)


def test_dead_zone_no_wasd():
    eng = _engine()
    intent = eng.update(_face(yaw=0.05, pitch=-0.04, mouth_open=0.1, left_ear=0.3, right_ear=0.3))
    assert intent.held_keys() == frozenset()


def test_head_right_holds_d():
    eng = _engine()
    intent = eng.update(_face(yaw=0.4, mouth_open=0.1, left_ear=0.3, right_ear=0.3))
    assert intent.held_keys() == frozenset({"d"})
    intent = eng.update(_face(yaw=0.4, mouth_open=0.1, left_ear=0.3, right_ear=0.3))
    assert "d" in intent.held_keys()
    intent = eng.update(_face(yaw=0.0, mouth_open=0.1, left_ear=0.3, right_ear=0.3))
    assert "d" not in intent.held_keys()


def test_head_left_up_diagonal():
    eng = _engine()
    intent = eng.update(_face(yaw=-0.4, pitch=0.4, mouth_open=0.1, left_ear=0.3, right_ear=0.3))
    assert intent.held_keys() == frozenset({"w", "a"})


def test_hysteresis_keeps_hold_inside_band():
    eng = _engine()
    eng.update(_face(yaw=0.4, mouth_open=0.1, left_ear=0.3, right_ear=0.3))
    intent = eng.update(_face(yaw=0.12, mouth_open=0.1, left_ear=0.3, right_ear=0.3))
    assert "d" in intent.held_keys()
    intent = eng.update(_face(yaw=0.05, mouth_open=0.1, left_ear=0.3, right_ear=0.3))
    assert "d" not in intent.held_keys()


def test_mouth_open_holds_space_until_closed():
    eng = _engine()
    assert "space" not in eng.update(_face(mouth_open=0.1, left_ear=0.3, right_ear=0.3)).held_keys()
    open_intent = eng.update(_face(mouth_open=0.5, left_ear=0.3, right_ear=0.3))
    assert open_intent.hold_space
    still = eng.update(_face(mouth_open=0.5, left_ear=0.3, right_ear=0.3))
    assert still.hold_space
    closed = eng.update(_face(mouth_open=0.1, left_ear=0.3, right_ear=0.3))
    assert not closed.hold_space


def test_wink_holds_l_blink_does_not():
    eng = _engine()
    blink = eng.update(_face(mouth_open=0.1, left_ear=0.08, right_ear=0.08))
    assert not blink.hold_l
    wink = eng.update(_face(mouth_open=0.1, left_ear=0.08, right_ear=0.30))
    assert wink.hold_l
    still = eng.update(_face(mouth_open=0.1, left_ear=0.08, right_ear=0.30))
    assert still.hold_l
    done = eng.update(_face(mouth_open=0.1, left_ear=0.30, right_ear=0.30))
    assert not done.hold_l


def test_face_lost_releases_everything():
    eng = _engine()
    eng.update(_face(yaw=0.4, pitch=0.4, mouth_open=0.6, left_ear=0.08, right_ear=0.30))
    lost = eng.update(FaceFeatures.none())
    assert lost.held_keys() == frozenset()


def test_calibrated_landmarks_map_to_wasd():
    eng = GestureEngine(make_test_config())
    for _ in range(5):
        eng.add_calibration_sample(extract_features(canonical_landmarks()))
    eng.finish_calibration()
    right = eng.update(extract_features(canonical_landmarks(nose_dx=0.10)))
    assert right.held_keys() == frozenset({"d"})
    up = GestureEngine(make_test_config())
    for _ in range(5):
        up.add_calibration_sample(extract_features(canonical_landmarks()))
    up.finish_calibration()
    up_intent = up.update(extract_features(canonical_landmarks(nose_dy=-0.12)))
    assert "w" in up_intent.held_keys()
