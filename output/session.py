"""Turn control state into held and tapped keys.

Semantics, decided from how EA Sports FC actually reads input:

- Movement (W/A/S/D) is continuous. Keys stay down while a direction is active
  and release the moment the nose returns to centre.
- Shooting is analogue. Its gesture holds Space, so a longer hold is a more
  powerful shot, matching how FC charges a strike.
- Passing is discrete. Its gesture taps L once; holding it never repeats.

Which gesture drives which action is not decided here. This module reads the
action table in `tracking.bindings` for the key and the hold-vs-tap rule, and
the active `BindingMap` for the channel to watch, so rebinding an action during
orientation needs no change to the output layer.

Safety is the priority over expressiveness: losing tracking, disarming, or
exiting always releases every held key, so a lost face can never leave the
player sprinting into a corner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Mapping

from output.keyboard import KeyboardBackend
from tracking.bindings import ACTIONS, Action, BindingMap, default_bindings
from tracking.controls import LEGACY_CHANNEL_KEYS

MOVEMENT_KEYS = ("W", "A", "S", "D")

# Kept so existing callers and tests keep importing a name rather than reaching
# into the action table. They are now derived, not authoritative: the action
# table decides the key.
SHOOT_KEY = ACTIONS["SHOOT"].key
PASS_KEY = ACTIONS["PASS"].key

# How long a tapped key stays down. Long enough for a browser to register it,
# short enough to feel instant at 30fps.
TAP_SECONDS = 0.08


@dataclass
class InputSession:
    """Diffs successive control states into key events.

    Disarmed by default. Nothing is ever pressed until `arm()` is called, so the
    system cannot type into a menu, a form, or someone's terminal by accident.
    """

    keyboard: KeyboardBackend
    # The map this session resolves actions against. Defaults to the shipped
    # mapping; Phase 5 loads a saved profile into it instead.
    bindings: BindingMap = field(default_factory=default_bindings)
    armed: bool = False
    _held: set[str] = field(default_factory=set)
    _tap_release_at: dict[str, float] = field(default_factory=dict)
    # Charge timer for the held action. SHOOT is the only action with a hold
    # trigger, so one timer is enough; a second hold action would need its own.
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
        self._tap_release_at.clear()
        self._last_shot_started = None
        self.shot_seconds = 0.0

    @property
    def held_keys(self) -> frozenset[str]:
        return frozenset(self._held)

    def apply(self, state: Mapping[str, object], *, now: float | None = None) -> None:
        """Apply one control state frame."""

        moment = monotonic() if now is None else now
        self._expire_taps(moment)

        if not self.armed or not state.get("tracking", False):
            self.release_all()
            return

        self._apply_movement(state)
        self._apply_actions(state, moment)

    def _apply_movement(self, state: Mapping[str, object]) -> None:
        raw = state.get("keys")
        wanted = {key for key in raw if key in MOVEMENT_KEYS} if isinstance(raw, list) else set()
        for key in MOVEMENT_KEYS:
            if key in wanted:
                self._press(key)
            else:
                self._release(key)

    def _apply_actions(self, state: Mapping[str, object], now: float) -> None:
        """Drive every action from whichever channel currently holds it.

        Iterating the action table rather than calling one method per action is
        what makes a rebind a data change. `ACTIONS` is ordered, so the key
        events for one frame come out in the same order every time.
        """

        for name, action in ACTIONS.items():
            channel = self.bindings.channel_for(name)
            if channel is None:
                # Rebinding displaces whatever held the channel, so an action
                # can legitimately be unbound mid-session. Release its key
                # rather than leaving it stuck down from the previous binding.
                self._release(action.key)
                continue
            view = self._channel_view(state, channel.name)
            if action.trigger == "hold":
                self._apply_hold(action, view, now)
            elif action.trigger == "tap":
                self._apply_tap(action, view, now)
            else:
                raise ValueError(f"{action.name}: unknown trigger {action.trigger!r}")

    @staticmethod
    def _channel_view(state: Mapping[str, object], channel_name: str) -> Mapping[str, object]:
        """Read one channel's gesture view out of a control state frame.

        Prefers the generic `channels` view. Falls back to the legacy top-level
        key for callers still emitting the pre-Phase-1 shape; both carry the
        same values, so the fallback changes nothing but tolerance.
        """

        channels = state.get("channels")
        if isinstance(channels, dict):
            view = channels.get(channel_name)
            if isinstance(view, dict):
                return view
        legacy = state.get(LEGACY_CHANNEL_KEYS.get(channel_name, channel_name))
        return legacy if isinstance(legacy, dict) else {}

    def _apply_hold(self, action: Action, view: Mapping[str, object], now: float) -> None:
        """Hold the key for as long as the gesture is active.

        Shot power in FC is charge duration, so the key must stay down for the
        whole gesture rather than being tapped on its rising edge.
        """

        if bool(view.get("active")):
            if action.key not in self._held:
                self._last_shot_started = now
            self._press(action.key)
            self.shot_seconds = now - (self._last_shot_started or now)
        else:
            self._release(action.key)
            self._last_shot_started = None
            self.shot_seconds = 0.0

    def _apply_tap(self, action: Action, view: Mapping[str, object], now: float) -> None:
        """Tap the key once per rising edge. `fired` is edged upstream.

        Guarding on `_held` as well means a gesture held across frames cannot
        retrigger while its tap is still being released.
        """

        if bool(view.get("fired")) and action.key not in self._held:
            self._press(action.key)
            self._tap_release_at[action.key] = now + TAP_SECONDS

    def _expire_taps(self, now: float) -> None:
        for key, due in list(self._tap_release_at.items()):
            if now >= due:
                self._release(key)

    def _press(self, key: str) -> None:
        if key in self._held:
            return
        self.keyboard.key_down(key)
        self._held.add(key)

    def _release(self, key: str) -> None:
        self._tap_release_at.pop(key, None)
        if key not in self._held:
            return
        self.keyboard.key_up(key)
        self._held.discard(key)
