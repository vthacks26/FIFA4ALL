"""Smoke test for the native MediaPipe vision stack.

Skipped automatically when the model bundle has not been downloaded, so the
pure-logic test suite still runs in minimal environments.
"""

import os

import numpy as np
import pytest

from fifa4all.vision.face_landmarks import DEFAULT_MODEL_PATH, FaceLandmarkerWrapper
from fifa4all.vision.head_pose import head_pose_from_matrix

pytestmark = pytest.mark.skipif(
    not os.path.isfile(DEFAULT_MODEL_PATH),
    reason="face_landmarker.task not downloaded (run scripts/download_models.sh)",
)


def test_landmarker_runs_headless_on_blank_frame():
    blank = np.zeros((240, 320, 3), dtype=np.uint8)
    with FaceLandmarkerWrapper() as landmarker:
        result = landmarker.detect(blank)
    # A blank frame has no face; the point is that the native pipeline executed.
    assert result.detected is False


def test_head_pose_matrix_extraction_is_neutral_for_identity():
    pose = head_pose_from_matrix(np.eye(4))
    assert abs(pose.yaw) < 1e-6
    assert abs(pose.pitch) < 1e-6
    assert abs(pose.roll) < 1e-6
