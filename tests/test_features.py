from fifa4all.vision.face_landmarks import head_pose_from_features
from fifa4all.vision.features import extract_features
from tests.helpers import canonical_landmarks


def test_missing_landmarks_not_detected():
    assert extract_features(None).detected is False
    assert extract_features(canonical_landmarks()[:10]).detected is False


def test_frontal_face_detected():
    feat = extract_features(canonical_landmarks())
    assert feat.detected
    assert abs(feat.yaw) < 0.05
    assert feat.pitch < 0
    assert 0.15 < feat.mouth_open < 0.35
    assert feat.left_ear > 0.2
    assert feat.right_ear > 0.2


def test_nose_right_increases_yaw():
    left = extract_features(canonical_landmarks(nose_dx=-0.08))
    right = extract_features(canonical_landmarks(nose_dx=0.08))
    assert right.yaw > 0.18
    assert left.yaw < -0.18
    assert right.yaw > left.yaw


def test_nose_up_increases_pitch():
    down = extract_features(canonical_landmarks(nose_dy=0.08))
    up = extract_features(canonical_landmarks(nose_dy=-0.08))
    assert up.pitch > down.pitch


def test_mouth_open_increases_mar():
    closed = extract_features(canonical_landmarks(mouth_open=0.03))
    opened = extract_features(canonical_landmarks(mouth_open=0.14))
    assert opened.mouth_open > closed.mouth_open
    assert opened.mouth_open > 0.5


def test_wink_lowers_one_ear_only():
    wink_left = extract_features(
        canonical_landmarks(left_eye_open=0.004, right_eye_open=0.03)
    )
    wink_right = extract_features(
        canonical_landmarks(left_eye_open=0.03, right_eye_open=0.004)
    )
    blink = extract_features(
        canonical_landmarks(left_eye_open=0.004, right_eye_open=0.004)
    )
    assert wink_left.left_ear < 0.16 < wink_left.right_ear
    assert wink_right.right_ear < 0.16 < wink_right.left_ear
    assert blink.left_ear < 0.16 and blink.right_ear < 0.16


def test_look_right_maps_to_positive_pr1_yaw_degrees():
    feat = extract_features(canonical_landmarks(nose_dx=0.08))
    pose = head_pose_from_features(feat)
    assert pose.yaw > 8.0
