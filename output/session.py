"""Turn control state into held and tapped keys.

Semantics, decided from how EA Sports FC actually reads input:

- Movement (W/A/S/D) is continuous. Keys stay down while a direction is active
  and release the moment the nose returns to centre.
- Shooting is analogue. Mouth-open holds Space, so a longer open is a more
  powerful shot, matching how FC charges a strike.
- Passing is a hold. Either-eye wink holds L until the eye opens again.

Safety is the priority over expressiveness: losing tracking, disarming, or
exiting always releases every held key, so a lost face can never leave the
player sprinting into a corner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Mapping

from output.keyboard import KeyboardBackend

MOVEMENT_KEYS = ("W", "A", "S", "D")
SHOOT_KEY = "Space"
PASS_KEY = "L"


@dataclass
class InputSession:
    """Diffs successive control states into key events.

    Disarmed by default. Nothing is ever pressed until `arm()` is called, so the
    system cannot type into a menu, a form, or someone's terminal by accident.
    """

    keyboard: KeyboardBackend
    armed: bool = False
    _held: set[str] = field(default_factory=set)
    _last_shot_started: float | None = None
    shot_seconds: float = 0.0

    def arm(self) -> None:
        self.armed = True

    def disarm(self) -> None:
        """Stop sending input and drop everything currently held."""

        self.armed = False
        self.release_all()

    def release_all(self) -> None:
        for key in sorted(self._held):
            self.keyboard.key_up(key)
        self._held.clear()
        self._last_shot_started = None
        self.shot_seconds = 0.0

    @property
    def held_keys(self) -> frozenset[str]:
        return frozenset(self._held)

    def apply(self, state: Mapping[str, object], *, now: float | None = None) -> None:
        """Apply one control state frame."""

        moment = monotonic() if now is None else now

        if not self.armed or not state.get("tracking", False):
            self.release_all()
            return

        self._apply_movement(state)
        self._apply_shoot(state, moment)
        self._apply_pass(state)

    def _apply_movement(self, state: Mapping[str, object]) -> None:
        raw = state.get("keys")
        wanted = {key for key in raw if key in MOVEMENT_KEYS} if isinstance(raw, list) else set()
        for key in MOVEMENT_KEYS:
            if key in wanted:
                self._press(key)
            else:
                self._release(key)

    def _apply_shoot(self, state: Mapping[str, object], now: float) -> None:
        """Mouth-open holds Space so shot power tracks how long it stays open."""

        mouth = state.get("mouth")
        active = bool(mouth.get("active")) if isinstance(mouth, dict) else False
        if active:
            if SHOOT_KEY not in self._held:
                self._last_shot_started = now
            self._press(SHOOT_KEY)
            self.shot_seconds = now - (self._last_shot_started or now)
        else:
            self._release(SHOOT_KEY)
            self._last_shot_started = None
            self.shot_seconds = 0.0

    def _apply_pass(self, state: Mapping[str, object]) -> None:
        """Either-eye wink holds L until the eye opens again."""

        wink = state.get("wink")
        active = bool(wink.get("active")) if isinstance(wink, dict) else False
        if active:
            self._press(PASS_KEY)
        else:
            self._release(PASS_KEY)

    def _press(self, key: str) -> None:
        if key in self._held:
            return
        self.keyboard.key_down(key)
        self._held.add(key)

    def _release(self, key: str) -> None:
        if key not in self._held:
            return
        self.keyboard.key_up(key)
        self._held.discard(key)
