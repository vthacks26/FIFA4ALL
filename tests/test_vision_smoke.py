"""Smoke test for MediaPipe Face Mesh (0.10.x). Skipped if solutions is missing."""

import numpy as np
import pytest

from fifa4all.vision.face_landmarks import FaceMeshTracker, head_pose_from_features
from fifa4all.vision.features import FaceFeatures
from fifa4all.vision.head_pose import head_pose_from_matrix

try:
    import mediapipe as mp

    HAS_SOLUTIONS = hasattr(mp, "solutions")
except Exception:  # pragma: no cover
    HAS_SOLUTIONS = False

pytestmark = pytest.mark.skipif(
    not HAS_SOLUTIONS,
    reason="mediapipe.solutions unavailable (need mediapipe>=0.10.14,<1)",
)


def test_face_mesh_runs_headless_on_blank_frame():
    blank = np.zeros((240, 320, 3), dtype=np.uint8)
    with FaceMeshTracker() as tracker:
        result = tracker.detect(blank)
    assert result.detected is False


def test_head_pose_matrix_extraction_is_neutral_for_identity():
    pose = head_pose_from_matrix(np.eye(4))
    assert abs(pose.yaw) < 1e-6
    assert abs(pose.pitch) < 1e-6
    assert abs(pose.roll) < 1e-6


def test_face_mesh_units_map_onto_pr1_dead_zone():
    pose = head_pose_from_features(FaceFeatures(True, yaw=0.18, pitch=0.16))
    assert abs(pose.yaw - 8.0) < 1e-6
    assert abs(pose.pitch + 8.0) < 1e-6  # look-up → negative PR #1 pitch → W
