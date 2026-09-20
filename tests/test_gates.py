"""Tests for confound gates on gesture channels.

A gate's job is to refuse a reading that could be the channel's known
confound rather than the gesture. These tests drive each confound directly and
assert the channel does not fire.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from tracking.bindings import CHANNELS, GestureChannel
from tracking.controls import ControlStateMachine

NOSE = (0.5, 0.5)
# A neutral face: every channel sitting at a plausible resting value.
REST = {
    "mouth_opening": 0.050,
    "head_turn": 0.000,
    "head_tilt": 0.000,
    "head_pitch": 0.250,
    "left_wink": 0.000,
    "left_eye_opening": 0.100,
    "right_eye_opening": 0.100,
    "brow_raise": 0.180,
    "mouth_width": 0.460,
    "mouth_pucker": 0.030,
    "jaw_lateral": 0.000,
    "cheek_span_ratio": 2.050,
}


def machine() -> ControlStateMachine:
    control = ControlStateMachine()
    control.calibrate(NOSE, mouth_rest=0.050, eye_rest=0.100, pitch_rest=0.250)
    return control


def drive(control: ControlStateMachine, **overrides: float) -> dict:
    """Hold a face pose for a few frames and return the last state."""

    state: dict = {}
    for index in range(4):
        state = control.update(
            nose=NOSE,
            features={**REST, **overrides},
            tracking_valid=True,
            now=float(index) / 30.0,
        )
    return state


class BrowRaiseHeadLevelGateTests(unittest.TestCase):
    def test_a_brow_raise_fires_while_the_head_is_level(self) -> None:
        state = drive(machine(), brow_raise=0.260)
        self.assertTrue(state["channels"]["brow_raise"]["active"])

    def test_steering_up_does_not_trip_a_brow_raise(self) -> None:
        """Pitch is the N/S steering axis, so it must not fake the gesture."""
        state = drive(machine(), brow_raise=0.260, head_pitch=0.150)
        self.assertFalse(state["channels"]["brow_raise"]["active"])
        self.assertTrue(state["channels"]["brow_raise"]["gated"])

    def test_an_uncalibrated_resting_pitch_refuses_to_fire(self) -> None:
        """Without a baseline the gate cannot be judged, so it must not pass."""
        control = ControlStateMachine()
        control.calibrate(NOSE, mouth_rest=0.050, eye_rest=0.100)
        state = drive(control, brow_raise=0.260)
        self.assertFalse(state["channels"]["brow_raise"]["active"])
        self.assertTrue(state["channels"]["brow_raise"]["gated"])


class SmileMouthNearRestGateTests(unittest.TestCase):
    def test_a_smile_fires_with_the_mouth_at_rest(self) -> None:
        state = drive(machine(), mouth_width=0.560)
        self.assertTrue(state["channels"]["smile_width"]["active"])

    def test_an_open_mouth_does_not_also_count_as_a_smile(self) -> None:
        """Shoot is bound to mouth_open; it must not fire pass as well."""
        state = drive(machine(), mouth_width=0.560, mouth_opening=0.200)
        self.assertFalse(state["channels"]["smile_width"]["active"])
        self.assertTrue(state["channels"]["smile_width"]["gated"])


class WinkPoseOcclusionGateTests(unittest.TestCase):
    def test_one_eye_open_also_rejects_a_tilt_covered_eye(self) -> None:
        control = machine()
        self.assertFalse(
            control.gate_passes(
                CHANNELS["wink"],
                {**REST, "left_wink": 0.105, "left_eye_opening": 0.005, "head_tilt": 40.0},
            )
        )

    def test_a_frontal_wink_still_clears_the_gate(self) -> None:
        control = machine()
        self.assertTrue(
            control.gate_passes(
                CHANNELS["wink"],
                {**REST, "left_wink": 0.095, "left_eye_opening": 0.005},
            )
        )


class JawLateralFacingForwardGateTests(unittest.TestCase):
    def test_a_jaw_slide_fires_while_facing_forward(self) -> None:
        state = drive(machine(), jaw_lateral=0.060)
        self.assertTrue(state["channels"]["jaw_lateral"]["active"])

    def test_a_head_turn_does_not_read_as_a_jaw_slide(self) -> None:
        state = drive(machine(), jaw_lateral=0.060, head_turn=0.200)
        self.assertFalse(state["channels"]["jaw_lateral"]["active"])
        self.assertTrue(state["channels"]["jaw_lateral"]["gated"])

    def test_either_direction_of_slide_is_the_same_gesture(self) -> None:
        self.assertTrue(CHANNELS["jaw_lateral"].use_magnitude)
        state = drive(machine(), jaw_lateral=-0.060)
        self.assertTrue(state["channels"]["jaw_lateral"]["active"])


class GateFailureModeTests(unittest.TestCase):
    def test_a_missing_feature_releases_rather_than_reading_as_rest(self) -> None:
        control = machine()
        drive(control, brow_raise=0.260)
        state = control.update(
            nose=NOSE,
            features={**REST, "brow_raise": None, "head_pitch": 0.250},  # type: ignore[dict-item]
            tracking_valid=True,
            now=1.0,
        )
        self.assertFalse(state["channels"]["brow_raise"]["active"])
        self.assertIsNone(state["channels"]["brow_raise"]["value"])

    def test_losing_tracking_releases_every_channel(self) -> None:
        control = machine()
        drive(control, brow_raise=0.260, jaw_lateral=0.060)
        state = control.update(nose=None, features={}, tracking_valid=False, now=2.0)
        for name, channel in state["channels"].items():
            self.assertFalse(channel["active"], name)

    def test_a_gated_channel_reports_no_confidence(self) -> None:
        """A meter climbing toward a threshold that cannot fire is a lie."""
        state = drive(machine(), brow_raise=0.260, head_pitch=0.150)
        self.assertEqual(state["channels"]["brow_raise"]["confidence"], 0.0)

    def test_an_unknown_gate_is_an_error_rather_than_a_silent_pass(self) -> None:
        control = machine()
        bogus = replace(CHANNELS["brow_raise"], gate="not_a_real_gate")
        with self.assertRaises(ValueError):
            control.gate_passes(bogus, REST)

    def test_every_registered_gate_name_is_implemented(self) -> None:
        control = machine()
        for channel in CHANNELS.values():
            if channel.gate is None:
                continue
            # Must not raise: an unimplemented gate would ship a guardless
            # channel to a player who relies on it.
            control.gate_passes(channel, REST)


class UngatedChannelTests(unittest.TestCase):
    def test_a_channel_without_a_confound_needs_no_gate(self) -> None:
        self.assertIsNone(CHANNELS["mouth_open"].gate)
        state = drive(machine(), mouth_opening=0.200)
        self.assertTrue(state["channels"]["mouth_open"]["active"])

    def test_channels_held_back_from_selection_are_still_measured(self) -> None:
        """Phase 4 scoring needs to see them even though nobody can pick them."""
        for name in ("cheek_puff", "mouth_pucker"):
            self.assertFalse(CHANNELS[name].selectable, name)
        state = drive(machine())
        self.assertIn("cheek_puff", state["channels"])
        self.assertIn("mouth_pucker", state["channels"])


if __name__ == "__main__":
    unittest.main()
