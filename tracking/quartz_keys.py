"""macOS HID keyboard events (Quartz CGEventPost).

Copied from cursor/face-control-mvp-3874: Luna in Chrome accepts these
OS-level holds, not DOM KeyboardEvents.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import AbstractSet, Protocol, runtime_checkable

MVP_KEYS = ("w", "a", "s", "d", "space", "l")

MAC_VIRTUAL_KEYCODES = {
    "a": 0x00,
    "s": 0x01,
    "d": 0x02,
    "w": 0x0D,
    "l": 0x25,
    "space": 0x31,
}
KCG_HID_EVENT_TAP = 0

LABEL_TO_KEY = {
    "W": "w",
    "A": "a",
    "S": "s",
    "D": "d",
    "L": "l",
    "Space": "space",
}


@runtime_checkable
class KeyInjector(Protocol):
    def press(self, key: str) -> None: ...
    def release(self, key: str) -> None: ...


@dataclass
class KeyEvent:
    time_s: float
    action: str
    key: str


class RecordingKeyInjector:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self.events: list[KeyEvent] = []

    def press(self, key: str) -> None:
        _validate_key(key)
        self.events.append(KeyEvent(float(self._clock()), "down", key))

    def release(self, key: str) -> None:
        _validate_key(key)
        self.events.append(KeyEvent(float(self._clock()), "up", key))


class QuartzKeyInjector:
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
            raise RuntimeError(f"CGEventCreateKeyboardEvent failed for {key}.")
        self._cg.CGEventPost(KCG_HID_EVENT_TAP, event)
        self._cf.CFRelease(event)


class HeldKeySession:
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


def labels_to_keys(labels: list[str]) -> frozenset[str]:
    return frozenset(LABEL_TO_KEY[label] for label in labels if label in LABEL_TO_KEY)


def _validate_key(key: str) -> None:
    if key not in MVP_KEYS:
        raise ValueError(f"Unsupported key {key!r}; MVP keys are {MVP_KEYS}")
