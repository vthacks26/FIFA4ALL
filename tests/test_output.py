"""Tests for the keyboard output layer.

Every test uses RecordingKeyboard, so no real key is ever pressed.
"""

from __future__ import annotations

import unittest

from output.keyboard import (
    KEY_CODES,
    RecordingKeyboard,
    accessibility_trusted,
    build_keyboard,
    probe_key_output,
)
from output.session import MOVEMENT_KEYS, PASS_KEY, SHOOT_KEY, TAP_SECONDS, InputSession
from dataclasses import replace

from tracking.bindings import ACTIONS, default_bindings
from output.session import (
    MOVEMENT_KEYS,
    PASS_KEY,
    PASS_PRESS_DELAY_SECONDS,
    SHOOT_KEY,
    SHOOT_PRESS_DELAY_SECONDS,
    InputSession,
)


def state(
    keys: list[str] | None = None,
    *,
    mouth: bool = False,
    wink: bool = False,
    wink_fired: bool = False,
    tracking: bool = True,
) -> dict[str, object]:
    return {
        "keys": keys or [],
        "mouth": {"active": mouth, "fired": False},
        "wink": {"active": wink, "fired": wink_fired},
        "tracking": tracking,
    }


def armed() -> tuple[InputSession, RecordingKeyboard]:
    keyboard = RecordingKeyboard()
    session = InputSession(keyboard)
    session.arm()
    return (session, keyboard)


def confirm_mouth(session: InputSession, start: float = 0.0) -> float:
    """Keep the mouth open through the 200ms Space delay. Returns key-down time."""

    session.apply(state(mouth=True), now=start)
    down_at = start + SHOOT_PRESS_DELAY_SECONDS
    session.apply(state(mouth=True), now=down_at)
    return down_at


def confirm_wink(session: InputSession, start: float = 0.0) -> float:
    """Keep the wink detected through the 200ms L delay. Returns key-down time."""

    session.apply(state(wink=True), now=start)
    down_at = start + PASS_PRESS_DELAY_SECONDS
    session.apply(state(wink=True), now=down_at)
    return down_at


class KeyCodeTests(unittest.TestCase):
    def test_every_key_the_session_uses_has_a_code(self) -> None:
        for key in (*MOVEMENT_KEYS, SHOOT_KEY, PASS_KEY):
            with self.subTest(key=key):
                self.assertIn(key, KEY_CODES)

    def test_movement_codes_are_the_wasd_cluster(self) -> None:
        self.assertEqual(
            [KEY_CODES[k] for k in ("W", "A", "S", "D")], [13, 0, 1, 2]
        )

    def test_build_keyboard_returns_a_usable_backend(self) -> None:
        keyboard = build_keyboard()
        self.assertTrue(hasattr(keyboard, "key_down"))
        self.assertTrue(hasattr(keyboard, "key_up"))

    def test_codes_agree_with_the_tracking_injector(self) -> None:
        """Two key injectors live in this repo; they must not disagree."""

        from tracking.quartz_keys import LABEL_TO_KEY, MAC_VIRTUAL_KEYCODES

        for label, name in LABEL_TO_KEY.items():
            with self.subTest(label=label):
                self.assertEqual(KEY_CODES[label], MAC_VIRTUAL_KEYCODES[name])


class PermissionProbeTests(unittest.TestCase):
    """The probe must never claim output works when macOS would discard it."""

    def test_accessibility_trusted_returns_a_tristate(self) -> None:
        self.assertIn(accessibility_trusted(), (True, False, None))

    def test_probe_reports_a_reason_when_it_fails(self) -> None:
        ok, message = probe_key_output()
        self.assertIsInstance(ok, bool)
        self.assertTrue(message, "a failing probe must explain itself")

    def test_untrusted_process_is_reported_as_blocked(self) -> None:
        if accessibility_trusted() is not False:
            self.skipTest("this process already has Accessibility permission")
        ok, message = probe_key_output()
        self.assertFalse(ok)
        self.assertIn("Accessibility", message)


class ArmingTests(unittest.TestCase):
    def test_a_new_session_is_disarmed(self) -> None:
        self.assertFalse(InputSession(RecordingKeyboard()).armed)

    def test_disarmed_session_presses_nothing(self) -> None:
        keyboard = RecordingKeyboard()
        session = InputSession(keyboard)
        session.apply(state(["W"], mouth=True, wink=True), now=0.0)
        self.assertEqual(keyboard.events, [])

    def test_disarming_releases_everything_held(self) -> None:
        session, keyboard = armed()
        session.apply(state(["W", "D"], mouth=True), now=0.0)
        session.apply(state(["W", "D"], mouth=True), now=SHOOT_PRESS_DELAY_SECONDS)
        keyboard.reset()
        session.disarm()
        self.assertEqual(keyboard.held, set())
        self.assertEqual(sorted(e[1] for e in keyboard.events), ["D", "Space", "W"])
        self.assertTrue(all(e[0] == "up" for e in keyboard.events))


class MovementTests(unittest.TestCase):
    def test_direction_holds_the_key_down(self) -> None:
        session, keyboard = armed()
        session.apply(state(["W"]), now=0.0)
        self.assertEqual(keyboard.events, [("down", "W")])
        self.assertEqual(keyboard.held, {"W"})

    def test_holding_the_same_direction_does_not_repeat_the_press(self) -> None:
        session, keyboard = armed()
        session.apply(state(["W"]), now=0.0)
        keyboard.reset()
        session.apply(state(["W"]), now=0.1)
        self.assertEqual(keyboard.events, [], "a held direction must not re-press")

    def test_diagonal_holds_two_keys(self) -> None:
        session, keyboard = armed()
        session.apply(state(["W", "D"]), now=0.0)
        self.assertEqual(keyboard.held, {"W", "D"})

    def test_changing_direction_releases_only_the_stale_key(self) -> None:
        session, keyboard = armed()
        session.apply(state(["W", "D"]), now=0.0)
        keyboard.reset()
        session.apply(state(["W", "A"]), now=0.1)
        self.assertIn(("up", "D"), keyboard.events)
        self.assertIn(("down", "A"), keyboard.events)
        self.assertNotIn(("up", "W"), keyboard.events)

    def test_returning_to_centre_releases_all_movement(self) -> None:
        session, keyboard = armed()
        session.apply(state(["W", "D"]), now=0.0)
        session.apply(state([]), now=0.1)
        self.assertEqual(keyboard.held, set())

    def test_non_movement_keys_in_the_state_are_ignored(self) -> None:
        session, keyboard = armed()
        session.apply(state(["W", "Space"]), now=0.0)
        self.assertEqual(keyboard.held, {"W"}, "Space is driven by the mouth, not keys")


class ShootTests(unittest.TestCase):
    def test_open_mouth_does_not_press_space_immediately(self) -> None:
        session, keyboard = armed()
        session.apply(state(mouth=True), now=0.0)
        self.assertEqual(keyboard.events, [])
        self.assertNotIn(SHOOT_KEY, session.held_keys)

    def test_closing_before_the_delay_never_presses_space(self) -> None:
        session, keyboard = armed()
        session.apply(state(mouth=True), now=0.0)
        session.apply(state(mouth=False), now=SHOOT_PRESS_DELAY_SECONDS - 0.001)
        self.assertEqual(keyboard.events, [])
        self.assertEqual(session.held_keys, frozenset())

    def test_space_goes_down_after_the_mouth_stays_open(self) -> None:
        session, keyboard = armed()
        confirm_mouth(session)
        self.assertEqual(keyboard.events, [("down", "Space")])

    def test_space_stays_down_while_the_mouth_is_open(self) -> None:
        session, keyboard = armed()
        down_at = confirm_mouth(session)
        keyboard.reset()
        session.apply(state(mouth=True), now=down_at + 0.3)
        self.assertEqual(keyboard.events, [])
        self.assertIn(SHOOT_KEY, session.held_keys)

    def test_closing_the_mouth_releases_space(self) -> None:
        session, keyboard = armed()
        down_at = confirm_mouth(session)
        keyboard.reset()
        session.apply(state(mouth=False), now=down_at + 0.2)
        self.assertEqual(keyboard.events, [("up", "Space")])

    def test_shot_power_starts_when_space_goes_down(self) -> None:
        session, _ = armed()
        session.apply(state(mouth=True), now=10.0)
        self.assertEqual(session.shot_seconds, 0.0)
        down_at = 10.0 + SHOOT_PRESS_DELAY_SECONDS
        session.apply(state(mouth=True), now=down_at)
        self.assertEqual(session.shot_seconds, 0.0)
        self.assertIn(SHOOT_KEY, session.held_keys)
        session.apply(state(mouth=True), now=down_at + 0.55)
        self.assertAlmostEqual(session.shot_seconds, 0.55, places=3)

    def test_shot_power_resets_after_release(self) -> None:
        session, _ = armed()
        confirm_mouth(session)
        session.apply(state(mouth=True), now=0.6)
        session.apply(state(mouth=False), now=0.7)
        self.assertEqual(session.shot_seconds, 0.0)

    def test_a_second_shot_measures_from_its_own_start(self) -> None:
        session, _ = armed()
        confirm_mouth(session, start=0.0)
        session.apply(state(mouth=False), now=1.0)
        confirm_mouth(session, start=5.0)
        session.apply(state(mouth=True), now=5.4)
        self.assertAlmostEqual(session.shot_seconds, 0.2, places=3)

    def test_a_new_open_restarts_the_delay(self) -> None:
        session, keyboard = armed()
        session.apply(state(mouth=True), now=0.0)
        session.apply(state(mouth=False), now=0.15)
        reopen = 0.16
        session.apply(state(mouth=True), now=reopen)
        session.apply(state(mouth=True), now=reopen + SHOOT_PRESS_DELAY_SECONDS - 0.01)
        self.assertEqual(keyboard.events, [])
        session.apply(state(mouth=True), now=reopen + SHOOT_PRESS_DELAY_SECONDS)
        self.assertEqual(keyboard.events, [("down", "Space")])


class PassTests(unittest.TestCase):
    def test_pass_uses_the_same_press_delay_as_shoot(self) -> None:
        self.assertEqual(PASS_PRESS_DELAY_SECONDS, SHOOT_PRESS_DELAY_SECONDS)
        self.assertEqual(PASS_PRESS_DELAY_SECONDS, 0.2)

    def test_wink_does_not_press_l_immediately(self) -> None:
        session, keyboard = armed()
        session.apply(state(wink=True), now=0.0)
        self.assertEqual(keyboard.events, [])
        self.assertNotIn(PASS_KEY, session.held_keys)

    def test_releasing_before_the_delay_never_presses_l(self) -> None:
        session, keyboard = armed()
        session.apply(state(wink=True), now=0.0)
        session.apply(state(wink=False), now=PASS_PRESS_DELAY_SECONDS - 0.001)
        self.assertEqual(keyboard.events, [])
        self.assertEqual(session.held_keys, frozenset())

    def test_l_goes_down_after_the_wink_stays_detected(self) -> None:
        session, keyboard = armed()
        confirm_wink(session)
        self.assertEqual(keyboard.events, [("down", "L")])

    def test_l_stays_down_while_the_wink_is_held(self) -> None:
        session, keyboard = armed()
        down_at = confirm_wink(session)
        keyboard.reset()
        session.apply(state(wink=True), now=down_at + 0.3)
        self.assertEqual(keyboard.events, [])
        self.assertIn(PASS_KEY, session.held_keys)

    def test_releasing_the_wink_releases_l(self) -> None:
        session, keyboard = armed()
        down_at = confirm_wink(session)
        keyboard.reset()
        session.apply(state(wink=False), now=down_at + 0.2)
        self.assertEqual(keyboard.events, [("up", "L")])
        self.assertEqual(session.held_keys, frozenset())

    def test_a_new_wink_restarts_the_delay(self) -> None:
        session, keyboard = armed()
        session.apply(state(wink=True), now=0.0)
        session.apply(state(wink=False), now=0.15)
        reopen = 0.16
        session.apply(state(wink=True), now=reopen)
        session.apply(state(wink=True), now=reopen + PASS_PRESS_DELAY_SECONDS - 0.01)
        self.assertEqual(keyboard.events, [])
        session.apply(state(wink=True), now=reopen + PASS_PRESS_DELAY_SECONDS)
        self.assertEqual(keyboard.events, [("down", "L")])


class SafetyTests(unittest.TestCase):
    def test_tracking_loss_releases_every_held_key(self) -> None:
        session, keyboard = armed()
        session.apply(state(["W", "D"], mouth=True), now=0.0)
        session.apply(state(["W", "D"], mouth=True), now=SHOOT_PRESS_DELAY_SECONDS)
        keyboard.reset()
        session.apply(state(["W", "D"], mouth=True, tracking=False), now=0.3)
        self.assertEqual(keyboard.held, set())
        self.assertTrue(all(event[0] == "up" for event in keyboard.events))

    def test_regaining_tracking_resumes_input(self) -> None:
        session, keyboard = armed()
        session.apply(state(["W"], tracking=False), now=0.0)
        keyboard.reset()
        session.apply(state(["W"]), now=0.1)
        self.assertEqual(keyboard.events, [("down", "W")])

    def test_session_stays_armed_across_a_tracking_dropout(self) -> None:
        session, _ = armed()
        session.apply(state(["W"], tracking=False), now=0.0)
        self.assertTrue(session.armed)

    def test_release_all_is_safe_to_call_twice(self) -> None:
        session, keyboard = armed()
        session.apply(state(["W"]), now=0.0)
        session.release_all()
        keyboard.reset()
        session.release_all()
        self.assertEqual(keyboard.events, [])


def bound_state(
    *,
    channel: str,
    active: bool = False,
    fired: bool = False,
    tracking: bool = True,
) -> dict[str, object]:
    """A control state in the generic shape the state machine now emits."""

    views = {name: {"active": False, "fired": False} for name in ("mouth_open", "wink")}
    views[channel] = {"active": active, "fired": fired}
    return {"keys": [], "channels": views, "tracking": tracking}


class BindingDrivenOutputTests(unittest.TestCase):
    """The key and the hold-vs-tap rule come from the action table, not here."""

    def test_session_defaults_to_the_shipped_bindings(self) -> None:
        self.assertEqual(
            InputSession(RecordingKeyboard()).bindings.as_dict(), default_bindings().as_dict()
        )

    def test_keys_are_taken_from_the_action_table(self) -> None:
        self.assertEqual(SHOOT_KEY, ACTIONS["SHOOT"].key)
        self.assertEqual(PASS_KEY, ACTIONS["PASS"].key)

    def test_generic_channel_view_drives_shoot_without_the_legacy_key(self) -> None:
        session, keyboard = armed()
        # Shoot has a 200ms press delay, so one frame is not yet a press.
        session.apply(bound_state(channel="mouth_open", active=True), now=0.0)
        session.apply(bound_state(channel="mouth_open", active=True), now=0.25)
        self.assertIn(SHOOT_KEY, keyboard.held)

    def test_generic_channel_view_drives_pass_without_the_legacy_key(self) -> None:
        session, keyboard = armed()
        # Pass has a 200ms press delay, so one frame is not yet a press.
        session.apply(bound_state(channel="wink", active=True), now=0.0)
        session.apply(bound_state(channel="wink", active=True), now=0.25)
        self.assertIn(PASS_KEY, keyboard.held)

    def test_rebound_shoot_holds_space_from_its_new_channel(self) -> None:
        keyboard = RecordingKeyboard()
        session = InputSession(keyboard, bindings=default_bindings().rebound("SHOOT", "wink"))
        session.arm()
        session.apply(bound_state(channel="wink", active=True), now=0.0)
        session.apply(bound_state(channel="wink", active=True), now=0.25)
        # The press delay follows the action, not the channel it moved to.
        self.assertIn(SHOOT_KEY, keyboard.held)

    def test_rebound_shoot_ignores_the_channel_it_left(self) -> None:
        keyboard = RecordingKeyboard()
        session = InputSession(keyboard, bindings=default_bindings().rebound("SHOOT", "wink"))
        session.arm()
        session.apply(bound_state(channel="mouth_open", active=True), now=0.0)
        self.assertNotIn(SHOOT_KEY, keyboard.held)

    def test_a_tap_trigger_fires_once_even_while_the_gesture_is_held(self) -> None:
        """No shipped action taps today, but the trigger is in the contract."""

        keyboard = RecordingKeyboard()
        session = InputSession(keyboard, bindings=default_bindings().rebound("PASS", "mouth_open"))
        session.arm()
        tapping = replace(ACTIONS["PASS"], trigger="tap")
        view = {"fired": True, "active": True}
        session._apply_tap(tapping, view, 0.0)
        session._apply_tap(tapping, {"fired": True, "active": True}, 0.01)
        self.assertEqual(keyboard.events.count(("down", PASS_KEY)), 1)

    def test_an_unbound_action_presses_nothing(self) -> None:
        """`rebound` leaves the displaced action unbound until it is rebound."""

        keyboard = RecordingKeyboard()
        session = InputSession(keyboard, bindings=default_bindings().rebound("SHOOT", "wink"))
        session.arm()
        session.apply(bound_state(channel="wink", active=True, fired=True), now=0.0)
        self.assertNotIn(PASS_KEY, keyboard.held)

    def test_legacy_state_shape_still_drives_both_actions(self) -> None:
        """The pre-Phase-1 wire shape has no `channels`; it must still play."""

        session, keyboard = armed()
        session.apply(state(mouth=True, wink=True), now=0.0)
        # Both actions wait 200ms before their key goes down.
        self.assertNotIn(PASS_KEY, keyboard.held)
        self.assertNotIn(SHOOT_KEY, keyboard.held)
        session.apply(state(mouth=True, wink=True), now=0.25)
        self.assertIn(PASS_KEY, keyboard.held)
        self.assertIn(SHOOT_KEY, keyboard.held)


if __name__ == "__main__":
    unittest.main()
