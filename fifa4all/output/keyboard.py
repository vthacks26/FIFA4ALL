"""Keyboard output abstraction (joe_plan.txt section 15).

The control layer only emits intent; this layer converts intent into key
press/release/tap events. Two backends are provided:

* ``LoggingBackend``  -- records events, works everywhere (headless CI, cloud).
* ``PynputBackend``   -- injects real OS keyboard events; used on the local Mac
                         that drives the browser running Amazon Luna.

``KeyboardController`` tracks which movement keys are currently held so that a
key is released as soon as the head returns to neutral -- this prevents the
"stuck key" failure called out in EVALS.md.
"""

from __future__ import annotations

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
        try:
            return KeyboardController(PynputBackend())
        except Exception:  # pragma: no cover - environment dependent
            pass
    return KeyboardController(LoggingBackend(echo=True))
