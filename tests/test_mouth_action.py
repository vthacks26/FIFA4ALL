from fifa4all.controls.mouth_action import MouthActionDetector


def test_fires_once_per_open_cycle():
    d = MouthActionDetector(open_threshold=0.5, close_threshold=0.3)
    assert d.update(0.1) is False          # closed
    assert d.update(0.9) is True           # opens -> fires once
    assert d.update(0.9) is False          # still open -> no spam
    assert d.update(0.95) is False
    assert d.update(0.1) is False          # closes -> re-arm
    assert d.update(0.9) is True           # opens again -> fires again


def test_hysteresis_prevents_flicker():
    d = MouthActionDetector(open_threshold=0.5, close_threshold=0.3)
    assert d.update(0.9) is True
    # Hovering between close and open thresholds must not re-arm or re-fire.
    assert d.update(0.4) is False
    assert d.update(0.6) is False
    assert d.update(0.4) is False


def test_invalid_thresholds_rejected():
    import pytest

    with pytest.raises(ValueError):
        MouthActionDetector(open_threshold=0.3, close_threshold=0.5)
