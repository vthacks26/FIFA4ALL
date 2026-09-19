from fifa4all.output.keyboard import KeyboardController, KeyEvent, LoggingBackend


def test_press_and_release_on_direction_change():
    backend = LoggingBackend()
    kb = KeyboardController(backend)

    kb.apply_directional({"D"})
    assert kb.held == frozenset({"D"})
    assert backend.events == [KeyEvent("press", "D")]

    # Switching to up-right should hold W in addition, keeping D pressed.
    kb.apply_directional({"D", "W"})
    assert kb.held == frozenset({"D", "W"})
    assert KeyEvent("press", "W") in backend.events
    assert KeyEvent("release", "D") not in backend.events


def test_returning_to_neutral_releases_all():
    backend = LoggingBackend()
    kb = KeyboardController(backend)
    kb.apply_directional({"A", "W"})
    kb.apply_directional(set())
    assert kb.held == frozenset()
    releases = {e.key for e in backend.events if e.action == "release"}
    assert releases == {"A", "W"}


def test_tap_records_single_event():
    backend = LoggingBackend()
    kb = KeyboardController(backend)
    kb.tap("SPACE")
    assert backend.events == [KeyEvent("tap", "SPACE")]
