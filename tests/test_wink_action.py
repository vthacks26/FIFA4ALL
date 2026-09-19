from fifa4all.controls.wink_action import WinkHoldDetector


def test_wink_holds_until_both_open():
    d = WinkHoldDetector()
    assert d.update(0.30, 0.30) is False
    assert d.update(0.10, 0.30) is True
    assert d.update(0.10, 0.30) is True
    assert d.update(0.30, 0.30) is False


def test_blink_does_not_hold_l():
    d = WinkHoldDetector()
    assert d.update(0.10, 0.10) is False
    assert d.update(0.10, 0.10) is False
