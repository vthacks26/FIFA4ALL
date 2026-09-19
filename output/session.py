"""Turn control state into held and tapped keys.

Semantics, decided from how EA Sports FC actually reads input:

- Movement (W/A/S/D) is continuous. Keys stay down while a direction is active
  and release the moment the nose returns to centre.
- Shooting is analogue. Its gesture holds Space, so a longer hold is a more
  powerful shot, matching how FC charges a strike. Space goes down only after
  the gesture has been held for the action's press delay, 200ms for shoot; a
  shorter gesture never presses. After that, FIFA's own charge curve runs —
  no pulsing or extra slowing.
- Passing is a hold. Its gesture holds L until the gesture ends, with no
  press delay.

Which gesture drives which action is not decided here. This module reads the
action table in `tracking.bindings` for the key, the hold-vs-tap rule and the
press delay, and the active `BindingMap` for the channel to watch, so rebinding
an action during orientation needs no change to the output layer.

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

# How long a tap holds its key down. Long enough for the game to register a
# discrete press, short enough that it never reads as a hold. No action uses
# the tap trigger today -- pass became a hold upstream -- but the trigger is
# still part of the action contract, so the timing lives here with it.
TAP_SECONDS = 0.06

# Kept so existing callers and tests keep importing a name rather than reaching
# into the action table. All three are now derived, not authoritative: the
# action table decides the key and the press delay.
SHOOT_KEY = ACTIONS["SHOOT"].key
PASS_KEY = ACTIONS["PASS"].key
SHOOT_PRESS_DELAY_SECONDS = ACTIONS["SHOOT"].press_delay_seconds


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
    # When each hold action's current hold began, keyed by action name.
    _hold_started: dict[str, float] = field(default_factory=dict)
    # When each action's gesture became active, which is earlier than the
    # hold start whenever the action has a press delay.
    _gesture_since: dict[str, float] = field(default_factory=dict)
    # Charge timer for the held action. SHOOT is the only action with a hold
    # trigger, so one timer is enough; a second hold action would need its own.
    _last_shot_started: float | None = None
    _shoot_open_since: float | None = None
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
        self._shoot_open_since = None
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
        """Hold the key while the gesture is active, after its press delay.

        Shot power in FC is charge duration, so the key stays down for the
        whole gesture rather than being tapped on its rising edge. The press
        delay exists so a brief gesture never starts a charge at all; it is a
        property of the action, not of the gesture, so an action keeps it
        wherever it is rebound.
        """

        if not bool(view.get("active")):
            self._gesture_since.pop(action.name, None)
            self._release(action.key)
            self._hold_started.pop(action.name, None)
            if action.name == "SHOOT":
                self._last_shot_started = None
                self.shot_seconds = 0.0
            return

        since = self._gesture_since.setdefault(action.name, now)
        if now < since + action.press_delay_seconds:
            # Active, but not yet held long enough to commit to a press.
            return

        if action.key not in self._held:
            self._hold_started[action.name] = now
        self._press(action.key)
        held = now - self._hold_started.get(action.name, now)
        if action.name == "SHOOT":
            # Charge is measured from key-down, not from the gesture starting,
            # so the press delay is not counted as charge. Shot power belongs
            # to SHOOT alone: every hold action keeps its own start time, and
            # sharing one timer let pass zero the charge mid-shot.
            self._last_shot_started = self._hold_started.get(action.name)
            self.shot_seconds = held

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
        if key not in self._held:
            return
        self.keyboard.key_up(key)
        self._held.discard(key)
