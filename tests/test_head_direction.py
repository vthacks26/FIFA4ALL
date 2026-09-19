from fifa4all.controls.head_direction import DirectionConfig, HeadDirectionClassifier


def make():
    return HeadDirectionClassifier(DirectionConfig(yaw_threshold=8.0, pitch_threshold=8.0))


def test_neutral_inside_dead_zone():
    c = make()
    assert c.classify(0.0, 0.0) == frozenset()
    assert c.classify(7.9, -7.9) == frozenset()  # just inside the dead zone


def test_cardinal_directions():
    c = make()
    assert c.classify(20.0, 0.0) == frozenset({"D"})   # look right
    assert c.classify(-20.0, 0.0) == frozenset({"A"})  # look left
    assert c.classify(0.0, -20.0) == frozenset({"W"})  # look up
    assert c.classify(0.0, 20.0) == frozenset({"S"})   # look down


def test_diagonals():
    c = make()
    assert c.classify(20.0, -20.0) == frozenset({"D", "W"})   # up-right
    assert c.classify(-20.0, -20.0) == frozenset({"A", "W"})  # up-left
    assert c.classify(-20.0, 20.0) == frozenset({"A", "S"})   # down-left


def test_threshold_is_exclusive_boundary():
    c = make()
    # Exactly at the threshold is still neutral; just beyond activates.
    assert c.classify(8.0, 0.0) == frozenset()
    assert c.classify(8.01, 0.0) == frozenset({"D"})
