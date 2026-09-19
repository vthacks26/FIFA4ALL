from pathlib import Path

import numpy as np

from fifa4all.app import main
from fifa4all.config import make_test_config
from fifa4all.controls.intent import GestureEngine
from fifa4all.ui.overlay import draw_overlay
from fifa4all.vision.features import extract_features
from tests.helpers import canonical_landmarks


def test_cli_replay_recording(tmp_path, capsys):
    fixture = Path("tests/fixtures/replay_mixed.json")
    code = main(["--replay", str(fixture), "--injector", "recording", "--print-events"])
    assert code == 0
    out = capsys.readouterr().out
    assert "down w" in out
    assert "down space" in out
    assert "0.100 down" in out or "0.100" in out


def test_cli_refuses_live_camera_on_linux():
    import sys

    if sys.platform == "darwin":
        return
    code = main([])
    assert code == 2


def test_overlay_renders(tmp_path):
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    frame[:] = (40, 30, 20)
    feat = extract_features(canonical_landmarks(nose_dx=0.1, mouth_open=0.14))
    engine = GestureEngine(make_test_config())
    for _ in range(3):
        engine.add_calibration_sample(extract_features(canonical_landmarks()))
    engine.finish_calibration()
    intent = engine.update(feat)
    vis = draw_overlay(frame, feat, intent, engine, status="TEST")
    assert vis.shape == frame.shape
    out = tmp_path / "overlay.png"
    import cv2

    cv2.imwrite(str(out), vis)
    assert out.stat().st_size > 1000
