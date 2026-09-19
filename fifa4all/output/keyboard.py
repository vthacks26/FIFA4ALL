"""OS-level key down/up injection.

Amazon Luna in Chrome does not treat page-level KeyboardEvents as player
input. This module posts HID-class OS events:

* macOS: Quartz ``CGEventCreateKeyboardEvent`` + ``CGEventPost(kCGHIDEventTap)``
* elsewhere: pynput (X11 / Win32) as a non-target fallback
* tests / Linux CI: ``RecordingKeyInjector`` (no OS events)

Hold duration is preserved by pairing press/release with gesture lifetime
via ``HeldKeySession``.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import AbstractSet, Protocol, runtime_checkable

from fifa4all.config import MVP_KEYS

# ANSI US virtual keycodes from Carbon HIToolbox Events.h
MAC_VIRTUAL_KEYCODES = {
    "a": 0x00,  # kVK_ANSI_A
    "s": 0x01,  # kVK_ANSI_S
    "d": 0x02,  # kVK_ANSI_D
    "w": 0x0D,  # kVK_ANSI_W
    "l": 0x25,  # kVK_ANSI_L
    "space": 0x31,  # kVK_Space
}

KCG_HID_EVENT_TAP = 0  # kCGHIDEventTap


@runtime_checkable
class KeyInjector(Protocol):
    def press(self, key: str) -> None: ...
    def release(self, key: str) -> None: ...


@dataclass
class KeyEvent:
    time_s: float
    action: str  # "down" | "up"
    key: str


class RecordingKeyInjector:
    """Headless injector used by tests and ``--injector recording``."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self.events: list[KeyEvent] = []

    def press(self, key: str) -> None:
        _validate_key(key)
        self.events.append(KeyEvent(float(self._clock()), "down", key))

    def release(self, key: str) -> None:
        _validate_key(key)
        self.events.append(KeyEvent(float(self._clock()), "up", key))


class LoggingKeyInjector:
    """Prints OS-equivalent down/up without posting events (dry-run)."""

    def __init__(self, quiet: bool = False) -> None:
        self.quiet = quiet
        self.events: list[KeyEvent] = []

    def press(self, key: str) -> None:
        _validate_key(key)
        self.events.append(KeyEvent(time.monotonic(), "down", key))
        if not self.quiet:
            print(f"KEY down {key}", flush=True)

    def release(self, key: str) -> None:
        _validate_key(key)
        self.events.append(KeyEvent(time.monotonic(), "up", key))
        if not self.quiet:
            print(f"KEY up   {key}", flush=True)


class QuartzKeyInjector:
    """macOS HID keyboard events via CoreGraphics (not DOM KeyboardEvents)."""

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("QuartzKeyInjector only works on macOS.")
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
        _validate_key(key)
        code = MAC_VIRTUAL_KEYCODES[key]
        event = self._cg.CGEventCreateKeyboardEvent(None, code, down)
        if not event:
            raise RuntimeError(
                f"CGEventCreateKeyboardEvent failed for {key}. "
                "Grant Accessibility permission (see MACOS.md)."
            )
        self._cg.CGEventPost(KCG_HID_EVENT_TAP, event)
        self._cf.CFRelease(event)


class PynputKeyInjector:
    """Fallback injector. On macOS pynput also uses Quartz CGEvent."""

    def __init__(self) -> None:
        try:
            from pynput.keyboard import Controller, Key
        except ImportError as exc:
            raise RuntimeError(
                "pynput is required for --injector pynput. "
                "Install dependencies from requirements.txt."
            ) from exc
        self._controller = Controller()
        self._space = Key.space

    def _token(self, key: str):
        _validate_key(key)
        return self._space if key == "space" else key

    def press(self, key: str) -> None:
        self._controller.press(self._token(key))

    def release(self, key: str) -> None:
        self._controller.release(self._token(key))


class HeldKeySession:
    """Diff desired held keys against current OS key state."""

    def __init__(self, injector: KeyInjector) -> None:
        self.injector = injector
        self._held: set[str] = set()

    def apply(self, keys: AbstractSet[str]) -> None:
        desired = set(keys)
        unknown = desired - set(MVP_KEYS)
        if unknown:
            raise ValueError(f"Unsupported keys: {sorted(unknown)}")
        for key in sorted(self._held - desired):
            self.injector.release(key)
            self._held.discard(key)
        for key in sorted(desired - self._held):
            self.injector.press(key)
            self._held.add(key)

    def held(self) -> frozenset[str]:
        return frozenset(self._held)

    def release_all(self) -> None:
        self.apply(set())


def _validate_key(key: str) -> None:
    if key not in MVP_KEYS:
        raise ValueError(f"Unsupported key {key!r}; MVP keys are {MVP_KEYS}")


def create_injector(kind: str = "auto", *, platform: str | None = None) -> KeyInjector:
    plat = platform if platform is not None else sys.platform
    kind = kind.lower().strip()
    if kind in {"recording"}:
        return RecordingKeyInjector()
    if kind in {"null", "dry-run", "dryrun", "log"}:
        return LoggingKeyInjector()
    if kind == "quartz":
        return QuartzKeyInjector()
    if kind == "pynput":
        return PynputKeyInjector()
    if kind == "auto":
        if plat == "darwin":
            return QuartzKeyInjector()
        return LoggingKeyInjector()
    raise ValueError(
        f"Unknown injector {kind!r}. Use auto, quartz, pynput, recording, or dry-run."
    )
