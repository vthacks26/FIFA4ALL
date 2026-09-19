"""Keyboard output abstraction (joe_plan.txt section 15).

The control layer only emits intent; this layer converts intent into key
press/release/tap events. Backends:

* ``LoggingBackend``  -- records events, works everywhere (headless CI, cloud).
* ``QuartzBackend``   -- macOS HID ``CGEventPost`` (what Luna actually accepts).
* ``PynputBackend``   -- fallback OS injection when Quartz is unavailable.

``KeyboardController`` tracks which movement keys are currently held so that a
key is released as soon as the head returns to neutral -- this prevents the
"stuck key" failure called out in EVALS.md.
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class KeyEvent:
    action: str  # "press" | "release" | "tap"
    key: str


class KeyboardBackend(ABC):
    @abstractmethod
    def press(self, key: str) -> None: ...

    @abstractmethod
    def release(self, key: str) -> None: ...

    def tap(self, key: str) -> None:
        self.press(key)
        self.release(key)


class LoggingBackend(KeyboardBackend):
    """Headless-safe backend that records every event (and optionally prints)."""

    def __init__(self, echo: bool = False):
        self.events: List[KeyEvent] = []
        self.echo = echo

    def _record(self, action: str, key: str) -> None:
        event = KeyEvent(action=action, key=key)
        self.events.append(event)
        if self.echo:
            print(f"[keyboard] {action:<7} {key}")

    def press(self, key: str) -> None:
        self._record("press", key)

    def release(self, key: str) -> None:
        self._record("release", key)

    def tap(self, key: str) -> None:
        self._record("tap", key)


# ANSI US virtual keycodes from Carbon HIToolbox Events.h
_MAC_VIRTUAL_KEYCODES = {
    "A": 0x00,
    "S": 0x01,
    "D": 0x02,
    "W": 0x0D,
    "L": 0x25,
    "SPACE": 0x31,
}
_KCG_HID_EVENT_TAP = 0


class QuartzBackend(KeyboardBackend):  # pragma: no cover - requires macOS
    """macOS HID keyboard events via CoreGraphics (not DOM KeyboardEvents)."""

    def __init__(self):
        if sys.platform != "darwin":
            raise RuntimeError("QuartzBackend only works on macOS.")
        import ctypes
        import ctypes.util

        cg_path = ctypes.util.find_library("CoreGraphics") or (
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
        cf_path = ctypes.util.find_library("CoreFoundation") or (
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        self._cg = ctypes.cdll.LoadLibrary(cg_path)
        self._cf = ctypes.cdll.LoadLibrary(cf_path)
        self._cg.CGEventCreateKeyboardEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint16,
            ctypes.c_bool,
        ]
        self._cg.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
        self._cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        self._cg.CGEventPost.restype = None
        self._cf.CFRelease.argtypes = [ctypes.c_void_p]
        self._cf.CFRelease.restype = None

    def press(self, key: str) -> None:
        self._post(key, True)

    def release(self, key: str) -> None:
        self._post(key, False)

    def _post(self, key: str, down: bool) -> None:
        code = _MAC_VIRTUAL_KEYCODES.get(key.upper() if key != "SPACE" else "SPACE")
        if code is None:
            raise ValueError(f"Unsupported key {key!r}")
        event = self._cg.CGEventCreateKeyboardEvent(None, code, down)
        if not event:
            raise RuntimeError("CGEventCreateKeyboardEvent failed.")
        self._cg.CGEventPost(_KCG_HID_EVENT_TAP, event)
        self._cf.CFRelease(event)


class PynputBackend(KeyboardBackend):  # pragma: no cover - requires a display
    """Real OS keyboard injection. Requires ``pynput`` and a display/session."""

    _SPECIAL = {"SPACE": "space", "L": "l"}

    def __init__(self):
        from pynput.keyboard import Controller, Key  # noqa: F401

        self._controller = Controller()

    def _resolve(self, key: str):
        from pynput.keyboard import Key

        if key.upper() == "SPACE":
            return Key.space
        return key.lower()

    def press(self, key: str) -> None:
        self._controller.press(self._resolve(key))

    def release(self, key: str) -> None:
        self._controller.release(self._resolve(key))


class KeyboardController:
    """Stateful driver that owns the currently-held movement keys."""

    def __init__(self, backend: KeyboardBackend):
        self.backend = backend
        self._held: set[str] = set()

    @property
    def held(self) -> frozenset[str]:
        return frozenset(self._held)

    def apply_directional(self, keys: Iterable[str]) -> None:
        """Hold exactly ``keys``; press newly-active keys, release the rest."""

        target = set(keys)
        for key in target - self._held:
            self.backend.press(key)
        for key in self._held - target:
            self.backend.release(key)
        self._held = target

    def tap(self, key: str) -> None:
        self.backend.tap(key)

    def release_all(self) -> None:
        self.apply_directional([])


def get_keyboard(prefer_real: bool = False) -> KeyboardController:
    """Build a controller, falling back to the logging backend when no display."""

    if prefer_real:
        if sys.platform == "darwin":
            try:
                return KeyboardController(QuartzBackend())
            except Exception:  # pragma: no cover - environment dependent
                pass
        try:
            return KeyboardController(PynputBackend())
        except Exception:  # pragma: no cover - environment dependent
            pass
    return KeyboardController(LoggingBackend(echo=True))
