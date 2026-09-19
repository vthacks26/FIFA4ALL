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

The permission check posts a key and listens for it. Creating an event tap is
not a sufficient test on its own: tap creation can succeed on a process that is
still barred from posting, which would report "ready" for a setup where nothing
actually works.
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
        """Return a human-readable problem, or None when output should work.

        Cached, because the probe costs a round trip and the answer only
        changes when the user grants permission and restarts the process.
        """

        global _PERMISSION_CACHE
        if _PERMISSION_CACHE is _UNCHECKED:
            ok, message = probe_key_output()
            _PERMISSION_CACHE = None if ok else message
        return _PERMISSION_CACHE


def build_keyboard() -> KeyboardBackend:
    """Real keyboard when Quartz is importable, recording backend otherwise."""

    try:
        return QuartzKeyboard()
    except ImportError:
        return RecordingKeyboard()


# F13 is absent from most Mac keyboards and bound to nothing, so the probe
# cannot type a character into whatever happens to be focused.
PROBE_KEY_CODE = 105
PROBE_TIMEOUT_SECONDS = 0.5

_UNCHECKED = object()
_PERMISSION_CACHE: Any = _UNCHECKED


def probe_key_output() -> tuple[bool, str]:
    """Post a key and listen for it. Returns (reached_macos, message)."""

    try:
        import Quartz  # type: ignore[import-not-found]
    except ImportError:
        return (
            False,
            "pyobjc-framework-Quartz is not installed. Run:\n"
            "  .venv-mediapipe/bin/pip install 'pyobjc-framework-Quartz>=10,<12'",
        )

    seen: list[int] = []

    def on_event(_proxy: Any, _type: Any, event: Any, _refcon: Any) -> Any:
        code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        if int(code) == PROBE_KEY_CODE:
            seen.append(int(code))
        return event

    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionListenOnly,
        Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
        on_event,
        None,
    )
    if tap is None:
        return (False, _DENIED_MESSAGE)

    source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    Quartz.CFRunLoopAddSource(
        Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes
    )
    Quartz.CGEventTapEnable(tap, True)

    Quartz.CGEventPost(
        Quartz.kCGHIDEventTap, Quartz.CGEventCreateKeyboardEvent(None, PROBE_KEY_CODE, True)
    )
    Quartz.CGEventPost(
        Quartz.kCGHIDEventTap, Quartz.CGEventCreateKeyboardEvent(None, PROBE_KEY_CODE, False)
    )
    Quartz.CFRunLoopRunInMode(
        Quartz.kCFRunLoopDefaultMode, PROBE_TIMEOUT_SECONDS, False
    )
    Quartz.CGEventTapEnable(tap, False)

    if seen:
        return (True, "synthetic key events reach macOS; Luna will receive them")
    return (False, _DENIED_MESSAGE)


_DENIED_MESSAGE = (
    "macOS is discarding synthetic key events, which is the usual reason keys "
    "do not reach Luna. Grant Accessibility permission to the app running this "
    "process (Terminal, iTerm or your IDE) in System Settings > Privacy & "
    "Security > Accessibility, restart that app, then verify with:\n"
    "  .venv-mediapipe/bin/python -m output.selftest"
)
