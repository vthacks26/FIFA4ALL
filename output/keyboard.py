"""Keyboard backends.

The control pipeline reports intent; this layer turns intent into key events.
Two backends implement the same protocol so every test runs without touching
the real keyboard:

- `QuartzKeyboard` posts macOS CGEvents at the HID tap, which is
  indistinguishable from real hardware to a browser running Amazon Luna.
- `RecordingKeyboard` records calls for assertions.

macOS silently drops injected events unless the host process has Accessibility
permission, which is the usual reason synthetic keys "do not reach Luna".
`QuartzKeyboard.permission_error()` reports that as a clear message instead of
failing invisibly.
"""

from __future__ import annotations

from typing import Any, Protocol

# macOS virtual key codes. These are physical positions, not characters.
KEY_CODES: dict[str, int] = {
    "W": 13,
    "A": 0,
    "S": 1,
    "D": 2,
    "L": 37,
    "Space": 49,
    "Return": 36,
    "Escape": 53,
}


class KeyboardBackend(Protocol):
    """Anything that can hold and release named keys."""

    def key_down(self, key: str) -> None: ...

    def key_up(self, key: str) -> None: ...


class RecordingKeyboard:
    """Test backend. Records events and tracks which keys are held."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []
        self.held: set[str] = set()

    def key_down(self, key: str) -> None:
        self.events.append(("down", key))
        self.held.add(key)

    def key_up(self, key: str) -> None:
        self.events.append(("up", key))
        self.held.discard(key)

    def reset(self) -> None:
        self.events.clear()
        self.held.clear()


class QuartzKeyboard:
    """Real macOS keyboard output via CGEvent."""

    def __init__(self) -> None:
        import Quartz  # type: ignore[import-not-found]

        self._quartz: Any = Quartz
        # The HID tap sits below the session tap, so events arrive as if typed.
        self._tap = Quartz.kCGHIDEventTap

    def key_down(self, key: str) -> None:
        self._post(key, True)

    def key_up(self, key: str) -> None:
        self._post(key, False)

    def _post(self, key: str, pressed: bool) -> None:
        code = KEY_CODES.get(key)
        if code is None:
            raise KeyError(f"no macOS key code mapped for {key!r}")
        event = self._quartz.CGEventCreateKeyboardEvent(None, code, pressed)
        self._quartz.CGEventPost(self._tap, event)

    @staticmethod
    def permission_error() -> str | None:
        """Return a human-readable problem, or None when output should work."""

        try:
            import Quartz  # type: ignore[import-not-found]  # noqa: F401
        except ImportError:
            return (
                "pyobjc-framework-Quartz is not installed. Run:\n"
                "  .venv-mediapipe/bin/pip install 'pyobjc-framework-Quartz>=10,<12'"
            )

        try:
            from ApplicationServices import AXIsProcessTrusted  # type: ignore[import-not-found]
        except ImportError:
            # Trust cannot be read without pyobjc-framework-ApplicationServices.
            # Output may still work; the caller verifies by watching the game.
            return None

        if not AXIsProcessTrusted():
            return (
                "macOS Accessibility permission is not granted, so synthetic key "
                "events are silently discarded. Grant it to the app running this "
                "process (Terminal, iTerm or your IDE) in System Settings > "
                "Privacy & Security > Accessibility, then restart that app."
            )
        return None


def build_keyboard() -> KeyboardBackend:
    """Real keyboard when Quartz is importable, recording backend otherwise."""

    try:
        return QuartzKeyboard()
    except ImportError:
        return RecordingKeyboard()
