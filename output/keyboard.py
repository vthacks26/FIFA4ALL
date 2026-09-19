"""Keyboard backends.

The control pipeline reports intent; this layer turns intent into key events.
Two backends implement the same protocol so every test runs without touching
the real keyboard:

- `QuartzKeyboard` posts macOS CGEvents at the HID tap, which is
  indistinguishable from real hardware to a browser running Amazon Luna.
- `RecordingKeyboard` records calls for assertions.

CoreGraphics is loaded through `ctypes` rather than pyobjc, an approach taken
from `tracking/quartz_keys.py` on cursor/tracking-quartz-live-a2a3. It removes
the third-party dependency entirely and, importantly, releases each event with
`CFRelease`, which a pyobjc-based version of this module was leaking.

macOS silently drops injected events unless the host process has Accessibility
permission, which is the usual reason synthetic keys "do not reach Luna".
`QuartzKeyboard.permission_error()` reports that as a clear message instead of
failing invisibly.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from typing import Any, Protocol

# macOS virtual key codes. These are physical positions, not characters.
KEY_CODES: dict[str, int] = {
    "A": 0x00,
    "S": 0x01,
    "D": 0x02,
    "W": 0x0D,
    "L": 0x25,
    "Space": 0x31,
    "Return": 0x24,
    "Escape": 0x35,
}

# CGEventPost tap location. The HID tap sits below the session tap, so events
# arrive as if they had been typed on the built-in keyboard.
_HID_EVENT_TAP = 0


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
    """Real macOS keyboard output via CGEvent, through ctypes."""

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("QuartzKeyboard only works on macOS")
        self._cg, self._cf = _load_frameworks()

    def key_down(self, key: str) -> None:
        self._post(key, True)

    def key_up(self, key: str) -> None:
        self._post(key, False)

    def _post(self, key: str, pressed: bool) -> None:
        code = KEY_CODES.get(key)
        if code is None:
            raise KeyError(f"no macOS key code mapped for {key!r}")
        event = self._cg.CGEventCreateKeyboardEvent(None, code, pressed)
        if not event:
            raise RuntimeError(f"CGEventCreateKeyboardEvent failed for {key!r}")
        try:
            self._cg.CGEventPost(_HID_EVENT_TAP, event)
        finally:
            # Without this every keypress leaks a CGEvent.
            self._cf.CFRelease(event)

    @staticmethod
    def permission_error() -> str | None:
        """Return a human-readable problem, or None when output should work."""

        ok, message = probe_key_output()
        return None if ok else message


def _load_frameworks() -> tuple[Any, Any]:
    """Load CoreGraphics and CoreFoundation with the signatures we need."""

    cg_path = ctypes.util.find_library("CoreGraphics") or (
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
    )
    cf_path = ctypes.util.find_library("CoreFoundation") or (
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    cg = ctypes.cdll.LoadLibrary(cg_path)
    cf = ctypes.cdll.LoadLibrary(cf_path)

    cg.CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]
    cg.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
    cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    cg.CGEventPost.restype = None
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    cf.CFRelease.restype = None
    return (cg, cf)


def accessibility_trusted() -> bool | None:
    """Whether this process may post synthetic events.

    None when the answer cannot be determined, which is not the same as False.
    """

    if sys.platform != "darwin":
        return None
    path = ctypes.util.find_library("ApplicationServices")
    if path is None:
        return None
    try:
        lib = ctypes.cdll.LoadLibrary(path)
        lib.AXIsProcessTrusted.argtypes = []
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
    except (OSError, AttributeError):
        return None
    return bool(lib.AXIsProcessTrusted())


def probe_key_output() -> tuple[bool, str]:
    """Check whether posted keys will reach macOS. Returns (ok, message)."""

    if sys.platform != "darwin":
        return (False, "keyboard output is only implemented for macOS")

    trusted = accessibility_trusted()
    if trusted is False:
        return (False, DENIED_MESSAGE)

    try:
        _load_frameworks()
    except OSError as error:
        return (False, f"could not load CoreGraphics: {error}")

    if trusted is None:
        return (
            True,
            "CoreGraphics loaded, but Accessibility trust could not be read; "
            "confirm by watching the game respond",
        )
    return (True, "synthetic key events reach macOS; Luna will receive them")


DENIED_MESSAGE = (
    "macOS is discarding synthetic key events, which is the usual reason keys "
    "do not reach Luna. Grant Accessibility permission to the app running this "
    "process (Terminal, iTerm or your IDE) in System Settings > Privacy & "
    "Security > Accessibility, restart that app, then verify with:\n"
    "  .venv-mediapipe/bin/python -m output.selftest"
)


def build_keyboard() -> KeyboardBackend:
    """Real keyboard when CoreGraphics is available, recording backend otherwise."""

    try:
        return QuartzKeyboard()
    except (OSError, RuntimeError):
        return RecordingKeyboard()
