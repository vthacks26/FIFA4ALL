"""Tests for the shared control state derivation."""

from __future__ import annotations

import unittest

from tracking.bindings import CHANNELS, default_bindings
from tracking.controls import (
    CARDINALS,
    DIRECTION_KEYS,
    EYEBROW_RECENTRE,
    LEGACY_CHANNEL_KEYS,
    ControlStateMachine,
    ControlThresholds,
    classify_direction,
    hold_labels,
    parse_deadzone_mode,
)

NEUTRAL = {"mouth_opening": 0.0, "left_wink": 0.0}
CENTER = (0.5, 0.5)


def machine() -> ControlStateMachine:
    state = ControlStateMachine()
    state.calibrate(CENTER)
    return state


def at(dx: float, dy: float) -> tuple[float, float]:
    return (CENTER[0] + dx, CENTER[1] + dy)


class ThresholdValidationTests(unittest.TestCase):
    def test_exit_radius_must_exceed_enter_radius(self) -> None:
        with self.assertRaises(ValueError):
            ControlThresholds(enter_radius=0.05, exit_radius=0.05)

    def test_follow_radius_must_exceed_exit_radius(self) -> None:
        with self.assertRaises(ValueError):
            ControlThresholds(exit_radius=0.08, follow_radius=0.08)

    def test_mouth_reset_must_be_below_open(self) -> None:
        with self.assertRaises(ValueError):
            ControlThresholds(mouth_open=0.09, mouth_reset=0.09)

    def test_wink_off_must_be_below_wink_on(self) -> None:
        with self.assertRaises(ValueError):
            ControlThresholds(wink_on=0.02, wink_off=0.03)

    def test_brow_off_must_be_below_brow_on(self) -> None:
        with self.assertRaises(ValueError):
            ControlThresholds(brow_on=0.030, brow_off=0.030)


class DirectionClassifierTests(unittest.TestCase):
    def test_classifies_all_eight_zones(self) -> None:
        cases = {
            "N": (0.0, -0.1), "NE": (0.1, -0.1), "E": (0.1, 0.0), "SE": (0.1, 0.1),
            "S": (0.0, 0.1), "SW": (-0.1, 0.1), "W": (-0.1, 0.0), "NW": (-0.1, -0.1),
        }
        for expected, offset in cases.items():
            with self.subTest(direction=expected):
                self.assertEqual(classify_direction(offset), expected)

    def test_negative_y_offset_means_the_user_looked_up(self) -> None:
        self.assertEqual(classify_direction((0.0, -0.2)), "N")

    def test_every_direction_maps_to_keys(self) -> None:
        for direction in DIRECTION_KEYS:
            self.assertTrue(DIRECTION_KEYS[direction])

    def test_diagonals_activate_two_keys(self) -> None:
        for direction in ("NE", "SE", "SW", "NW"):
            with self.subTest(direction=direction):
                self.assertEqual(len(DIRECTION_KEYS[direction]), 2)

    def test_cardinals_activate_one_key(self) -> None:
        for direction in CARDINALS:
            with self.subTest(direction=direction):
                self.assertEqual(len(DIRECTION_KEYS[direction]), 1)


class DeadZoneTests(unittest.TestCase):
    def test_nose_at_center_releases_all_movement_keys(self) -> None:
        state = machine().update(nose=CENTER, features=NEUTRAL, tracking_valid=True)
        self.assertTrue(state["centered"])
        self.assertEqual(state["keys"], [])
        self.assertIsNone(state["direction"])

    def test_nose_outside_dead_zone_activates_direction(self) -> None:
        state = machine().update(nose=at(0.0, -0.12), features=NEUTRAL, tracking_valid=True)
        self.assertFalse(state["centered"])
        self.assertEqual(state["direction"], "N")
        self.assertEqual(state["keys"], ["W"])

    def test_diagonal_offset_activates_two_keys(self) -> None:
        state = machine().update(nose=at(0.12, -0.12), features=NEUTRAL, tracking_valid=True)
        self.assertEqual(state["direction"], "NE")
        self.assertEqual(state["keys"], ["W", "D"])

    def test_calibration_makes_the_calibrated_point_neutral(self) -> None:
        state = ControlStateMachine()
        state.calibrate((0.2, 0.8))
        result = state.update(nose=(0.2, 0.8), features=NEUTRAL, tracking_valid=True)
        self.assertTrue(result["centered"])

    def test_first_frame_without_calibration_becomes_the_center(self) -> None:
        state = ControlStateMachine()
        result = state.update(nose=(0.3, 0.7), features=NEUTRAL, tracking_valid=True)
        self.assertTrue(result["centered"])


class HysteresisTests(unittest.TestCase):
    def test_small_motion_near_the_boundary_does_not_chatter(self) -> None:
        state = machine()
        thresholds = state.thresholds
        # Sit between the enter and exit radii, where chatter would occur.
        between = (thresholds.enter_radius + thresholds.exit_radius) / 2.0

        self.assertTrue(
            state.update(nose=at(between, 0.0), features=NEUTRAL, tracking_valid=True)["centered"],
            "should not start moving before crossing the exit radius",
        )
        state.update(nose=at(thresholds.exit_radius + 0.02, 0.0), features=NEUTRAL, tracking_valid=True)
        self.assertFalse(
            state.update(nose=at(between, 0.0), features=NEUTRAL, tracking_valid=True)["centered"],
            "should keep moving until it falls back inside the enter radius",
        )

    def test_returning_to_center_reliably_releases_keys(self) -> None:
        state = machine()
        state.update(nose=at(0.2, 0.0), features=NEUTRAL, tracking_valid=True)
        result = state.update(nose=CENTER, features=NEUTRAL, tracking_valid=True)
        self.assertEqual(result["keys"], [])
        self.assertTrue(result["centered"])


class ZoneHysteresisTests(unittest.TestCase):
    """A nose resting on a zone boundary must not flap between directions."""

    def offset_at(self, degrees_ccw: float, radius: float = 0.12) -> tuple[float, float]:
        from math import cos, radians, sin

        angle = radians(degrees_ccw)
        # Image y grows downward, so negate to treat degrees as compass-style.
        return at(radius * cos(angle), -radius * sin(angle))

    def test_direction_holds_just_past_the_zone_boundary(self) -> None:
        state = machine()
        state.update(nose=self.offset_at(90.0), features=NEUTRAL, tracking_valid=True)
        self.assertEqual(state._direction, "N")
        # 60 degrees is raw NE, but still inside N once widened by the margin.
        result = state.update(nose=self.offset_at(60.0), features=NEUTRAL, tracking_valid=True)
        self.assertEqual(result["direction"], "N", "should not flap on the boundary")

    def test_direction_changes_once_the_margin_is_cleared(self) -> None:
        state = machine()
        state.update(nose=self.offset_at(90.0), features=NEUTRAL, tracking_valid=True)
        result = state.update(nose=self.offset_at(50.0), features=NEUTRAL, tracking_valid=True)
        self.assertEqual(result["direction"], "NE", "a deliberate move must still turn")

    def test_fresh_entry_uses_the_plain_classifier(self) -> None:
        # Same angle the held-direction test uses, but with no prior direction,
        # so the margin does not apply and the raw zone wins.
        state = machine()
        result = state.update(nose=self.offset_at(60.0), features=NEUTRAL, tracking_valid=True)
        self.assertEqual(result["direction"], "NE")

    def test_margin_must_stay_inside_half_a_zone(self) -> None:
        with self.assertRaises(ValueError):
            ControlThresholds(angle_margin=22.5)

    def test_margin_is_published_to_the_ui(self) -> None:
        self.assertIn("angle_margin", ControlThresholds().as_dict())


class DriftRecentreTests(unittest.TestCase):
    """Posture settles over time; a held-still nose outside centre is drift."""

    DRIFTED = at(0.0, -0.12)

    def test_holding_still_off_centre_recentres(self) -> None:
        state = machine()
        state.update(nose=self.DRIFTED, features=NEUTRAL, tracking_valid=True, now=0.0)
        result = state.update(nose=self.DRIFTED, features=NEUTRAL, tracking_valid=True, now=4.0)
        self.assertTrue(result["recentred"])
        self.assertTrue(result["centered"], "movement must stop once re-centred")

    def test_does_not_recentre_before_the_window(self) -> None:
        state = machine()
        state.update(nose=self.DRIFTED, features=NEUTRAL, tracking_valid=True, now=0.0)
        result = state.update(nose=self.DRIFTED, features=NEUTRAL, tracking_valid=True, now=2.0)
        self.assertFalse(result["recentred"])
        self.assertEqual(result["direction"], "N")

    def test_steering_resets_the_stillness_window(self) -> None:
        """A player actively steering keeps moving and must not be re-centred."""

        state = machine()
        for step in range(10):
            # Nudge the nose each frame, as a steering hand would.
            nose = at(0.0, -0.12 - step * 0.004)
            result = state.update(nose=nose, features=NEUTRAL, tracking_valid=True, now=step * 0.6)
            self.assertFalse(result["recentred"], f"steering re-centred at step {step}")

    def test_centred_nose_never_recentres(self) -> None:
        state = machine()
        state.update(nose=CENTER, features=NEUTRAL, tracking_valid=True, now=0.0)
        result = state.update(nose=CENTER, features=NEUTRAL, tracking_valid=True, now=9.0)
        self.assertFalse(result["recentred"])

    def test_tracking_loss_resets_the_stillness_window(self) -> None:
        state = machine()
        state.update(nose=self.DRIFTED, features=NEUTRAL, tracking_valid=True, now=0.0)
        state.update(nose=None, features={}, tracking_valid=False, now=1.0)
        result = state.update(nose=self.DRIFTED, features=NEUTRAL, tracking_valid=True, now=4.0)
        self.assertFalse(result["recentred"], "the window must restart after a dropout")

    def test_auto_recentre_can_be_disabled(self) -> None:
        state = machine()
        state.auto_recentre = False
        state.update(nose=self.DRIFTED, features=NEUTRAL, tracking_valid=True, now=0.0)
        result = state.update(nose=self.DRIFTED, features=NEUTRAL, tracking_valid=True, now=9.0)
        self.assertFalse(result["recentred"])
        self.assertEqual(result["direction"], "N")

    def test_recentred_flag_is_only_true_on_the_frame_it_happens(self) -> None:
        state = machine()
        state.update(nose=self.DRIFTED, features=NEUTRAL, tracking_valid=True, now=0.0)
        state.update(nose=self.DRIFTED, features=NEUTRAL, tracking_valid=True, now=4.0)
        after = state.update(nose=self.DRIFTED, features=NEUTRAL, tracking_valid=True, now=4.1)
        self.assertFalse(after["recentred"])

    def test_thresholds_reject_a_non_positive_window(self) -> None:
        with self.assertRaises(ValueError):
            ControlThresholds(recentre_seconds=0.0)


class MouthEdgeTriggerTests(unittest.TestCase):
    def test_crossing_the_threshold_fires_once(self) -> None:
        state = machine()
        first = state.update(nose=CENTER, features={**NEUTRAL, "mouth_opening": 0.2}, tracking_valid=True)
        self.assertTrue(first["mouth"]["fired"])

    def test_holding_the_mouth_open_does_not_refire(self) -> None:
        state = machine()
        state.update(nose=CENTER, features={**NEUTRAL, "mouth_opening": 0.2}, tracking_valid=True)
        held = state.update(nose=CENTER, features={**NEUTRAL, "mouth_opening": 0.2}, tracking_valid=True)
        self.assertFalse(held["mouth"]["fired"])
        self.assertTrue(held["mouth"]["active"])

    def test_mouth_refires_only_after_dropping_below_reset(self) -> None:
        state = machine()
        state.update(nose=CENTER, features={**NEUTRAL, "mouth_opening": 0.2}, tracking_valid=True)
        state.update(nose=CENTER, features={**NEUTRAL, "mouth_opening": 0.0}, tracking_valid=True)
        again = state.update(nose=CENTER, features={**NEUTRAL, "mouth_opening": 0.2}, tracking_valid=True)
        self.assertTrue(again["mouth"]["fired"])

    def test_value_between_reset_and_open_stays_latched(self) -> None:
        state = machine()
        thresholds = state.thresholds
        state.update(nose=CENTER, features={**NEUTRAL, "mouth_opening": 0.2}, tracking_valid=True)
        between = (thresholds.mouth_reset + thresholds.mouth_open) / 2.0
        held = state.update(nose=CENTER, features={**NEUTRAL, "mouth_opening": between}, tracking_valid=True)
        self.assertTrue(held["mouth"]["active"])
        self.assertFalse(held["mouth"]["fired"])


class RestingMouthCalibrationTests(unittest.TestCase):
    """A resting mouth does not read zero, and must still clear the latch."""

    def test_defaults_are_unchanged_without_calibration(self) -> None:
        self.assertEqual(machine().mouth_thresholds, (0.09, 0.06))

    def test_a_high_resting_mouth_raises_the_release_threshold(self) -> None:
        state = machine()
        state.calibrate(CENTER, mouth_rest=0.064)
        _, reset = state.mouth_thresholds
        self.assertGreater(reset, 0.064, "resting must fall below the release point")

    def test_resting_value_releases_the_latch_after_calibration(self) -> None:
        state = machine()
        state.calibrate(CENTER, mouth_rest=0.064)
        state.update(
            nose=CENTER, features={"mouth_opening": 0.2, "left_wink": 0.0},
            tracking_valid=True, now=0.0,
        )
        result = state.update(
            nose=CENTER, features={"mouth_opening": 0.064, "left_wink": 0.0},
            tracking_valid=True, now=0.5,
        )
        self.assertFalse(result["mouth"]["active"], "Space would stick open in game")

    def test_a_low_resting_mouth_keeps_the_tuned_thresholds(self) -> None:
        state = machine()
        state.calibrate(CENTER, mouth_rest=0.01)
        self.assertEqual(state.mouth_thresholds, (0.09, 0.06))

    def test_open_always_stays_above_reset(self) -> None:
        for rest in (0.0, 0.05, 0.1, 0.3):
            with self.subTest(rest=rest):
                state = machine()
                state.calibrate(CENTER, mouth_rest=rest)
                open_value, reset = state.mouth_thresholds
                self.assertGreater(open_value, reset)

    def test_calibrating_without_a_mouth_sample_leaves_thresholds_alone(self) -> None:
        state = machine()
        state.calibrate(CENTER)
        self.assertEqual(state.mouth_thresholds, (0.09, 0.06))


class GestureDurationTests(unittest.TestCase):
    """Shot power comes from how long the mouth stays open."""

    OPEN = {"mouth_opening": 0.2, "left_wink": 0.0}

    def test_hold_duration_accumulates_while_the_mouth_is_open(self) -> None:
        state = machine()
        state.update(nose=CENTER, features=self.OPEN, tracking_valid=True, now=10.0)
        result = state.update(nose=CENTER, features=self.OPEN, tracking_valid=True, now=10.8)
        self.assertAlmostEqual(result["mouth"]["held_seconds"], 0.8, places=2)

    def test_hold_duration_is_zero_when_closed(self) -> None:
        state = machine()
        result = state.update(nose=CENTER, features=NEUTRAL, tracking_valid=True, now=1.0)
        self.assertEqual(result["mouth"]["held_seconds"], 0.0)

    def test_hold_duration_resets_after_release(self) -> None:
        state = machine()
        state.update(nose=CENTER, features=self.OPEN, tracking_valid=True, now=0.0)
        state.update(nose=CENTER, features=self.OPEN, tracking_valid=True, now=1.0)
        result = state.update(nose=CENTER, features=NEUTRAL, tracking_valid=True, now=1.1)
        self.assertEqual(result["mouth"]["held_seconds"], 0.0)

    def test_duration_is_reported_regardless_of_input_arming(self) -> None:
        """The UI must show real gesture timing even with output disarmed."""

        state = machine()
        state.update(nose=CENTER, features=self.OPEN, tracking_valid=True, now=0.0)
        result = state.update(nose=CENTER, features=self.OPEN, tracking_valid=True, now=0.5)
        self.assertGreater(result["mouth"]["held_seconds"], 0.0)

    def test_tracking_loss_clears_the_duration(self) -> None:
        state = machine()
        state.update(nose=CENTER, features=self.OPEN, tracking_valid=True, now=0.0)
        result = state.update(nose=None, features={}, tracking_valid=False, now=1.0)
        self.assertEqual(result["mouth"]["held_seconds"], 0.0)


class WinkEdgeTriggerTests(unittest.TestCase):
    """`left_wink` is signed, so either eye must be able to fire a pass."""

    def wink(self, state: ControlStateMachine, value: float) -> dict[str, object]:
        return state.update(
            nose=CENTER, features={**NEUTRAL, "left_wink": value}, tracking_valid=True
        )

    def test_wink_fires_once_per_activation(self) -> None:
        state = machine()
        first = self.wink(state, 0.1)
        held = self.wink(state, 0.1)
        self.assertTrue(first["wink"]["fired"])
        self.assertFalse(held["wink"]["fired"], "eye held closed must not repeat the pass action")

    def test_left_eye_fires_a_pass(self) -> None:
        result = self.wink(machine(), 0.1)
        self.assertTrue(result["wink"]["fired"])
        self.assertEqual(result["wink"]["eye"], "left")

    def test_right_eye_fires_a_pass(self) -> None:
        """A right wink is negative, and used to be unable to cross the threshold."""

        result = self.wink(machine(), -0.1)
        self.assertTrue(result["wink"]["fired"])
        self.assertEqual(result["wink"]["eye"], "right")

    def test_either_eye_works_in_the_same_session(self) -> None:
        state = machine()
        self.assertTrue(self.wink(state, 0.1)["wink"]["fired"])
        self.wink(state, 0.0)
        self.assertTrue(self.wink(state, -0.1)["wink"]["fired"])

    def test_blinking_both_eyes_does_not_fire(self) -> None:
        """Both eyes close together, so the difference stays near zero."""

        result = self.wink(machine(), 0.002)
        self.assertFalse(result["wink"]["fired"])
        self.assertIsNone(result["wink"]["eye"])

    def test_confidence_is_positive_for_a_right_wink(self) -> None:
        result = self.wink(machine(), -0.02)
        self.assertGreater(result["wink"]["confidence"], 0.0)

    def test_neutral_eyes_report_no_winking_eye(self) -> None:
        self.assertIsNone(self.wink(machine(), 0.0)["wink"]["eye"])


class BlinkRejectionTests(unittest.TestCase):
    """Eyelids do not close in sync, so a blink briefly looks like a wink."""

    # Captured from a real blink on a MacBook FaceTime camera, as
    # (left_eye_opening, right_eye_opening) normalized by face width. Frame
    # four is the problem: the left eye is shut while the right lags half
    # open, a difference of 0.0508 against a 0.025 threshold.
    REAL_BLINK = [
        (0.0874, 0.0939),
        (0.0499, 0.0578),
        (0.0162, 0.0328),
        (0.0043, 0.0551),
        (0.0626, 0.0702),
    ]
    EYE_REST = 0.11

    def calibrated(self) -> ControlStateMachine:
        state = ControlStateMachine()
        state.calibrate(CENTER, eye_rest=self.EYE_REST)
        return state

    def eyes(self, left: float, right: float) -> dict[str, float]:
        return {
            "mouth_opening": 0.0,
            "left_wink": right - left,
            "left_eye_opening": left,
            "right_eye_opening": right,
        }

    def test_a_real_blink_never_fires_a_pass(self) -> None:
        state = self.calibrated()
        for index, (left, right) in enumerate(self.REAL_BLINK):
            result = state.update(
                nose=CENTER, features=self.eyes(left, right),
                tracking_valid=True, now=index * 0.033,
            )
            self.assertFalse(
                result["wink"]["fired"], f"blink frame {index} fired a pass"
            )

    def test_the_worst_blink_frame_alone_does_not_fire(self) -> None:
        """This frame's difference is double the wink threshold."""

        result = self.calibrated().update(
            nose=CENTER, features=self.eyes(0.0043, 0.0551), tracking_valid=True, now=0.0
        )
        self.assertFalse(result["wink"]["fired"])
        self.assertIsNone(result["wink"]["eye"])

    def test_a_genuine_wink_still_fires(self) -> None:
        """One eye shut while the other stays properly open."""

        result = self.calibrated().update(
            nose=CENTER, features=self.eyes(0.005, 0.11), tracking_valid=True, now=0.0
        )
        self.assertTrue(result["wink"]["fired"])
        self.assertEqual(result["wink"]["eye"], "left")

    def test_a_genuine_right_wink_still_fires(self) -> None:
        result = self.calibrated().update(
            nose=CENTER, features=self.eyes(0.11, 0.005), tracking_valid=True, now=0.0
        )
        self.assertTrue(result["wink"]["fired"])
        self.assertEqual(result["wink"]["eye"], "right")

    def test_gate_scales_to_a_narrow_eyed_user(self) -> None:
        """A user whose open eye reads low must still be able to wink."""

        state = ControlStateMachine()
        state.calibrate(CENTER, eye_rest=0.06)
        result = state.update(
            nose=CENTER, features=self.eyes(0.003, 0.06), tracking_valid=True, now=0.0
        )
        self.assertTrue(result["wink"]["fired"])

    def test_uncalibrated_gate_uses_the_documented_floor(self) -> None:
        state = ControlStateMachine()
        self.assertEqual(state.eye_open_gate(), state.thresholds.eye_open_floor)

    def test_missing_eye_openings_do_not_drop_every_wink(self) -> None:
        """Older feature payloads lack the absolute openings."""

        state = self.calibrated()
        result = state.update(
            nose=CENTER, features={"mouth_opening": 0.0, "left_wink": 0.1},
            tracking_valid=True, now=0.0,
        )
        self.assertTrue(result["wink"]["fired"])

    def test_eye_open_fraction_must_be_a_fraction(self) -> None:
        with self.assertRaises(ValueError):
            ControlThresholds(eye_open_fraction=1.0)


class TiltOcclusionTests(unittest.TestCase):
    """A head tilt or turn that covers an eye must not count as a wink."""

    EYE_REST = 0.11

    def calibrated(self) -> ControlStateMachine:
        state = ControlStateMachine()
        state.calibrate(CENTER, eye_rest=self.EYE_REST)
        return state

    def eyes(
        self,
        left: float,
        right: float,
        *,
        head_tilt: float = 0.0,
        head_turn: float = 0.0,
    ) -> dict[str, float]:
        return {
            "mouth_opening": 0.0,
            "left_wink": right - left,
            "left_eye_opening": left,
            "right_eye_opening": right,
            "head_tilt": head_tilt,
            "head_turn": head_turn,
        }

    def test_a_tilt_covered_eye_does_not_fire_a_pass(self) -> None:
        """One eye collapsed by roll looks like a wink; pose says it is not."""

        result = self.calibrated().update(
            nose=CENTER,
            features=self.eyes(0.005, 0.11, head_tilt=40.0),
            tracking_valid=True,
            now=0.0,
        )
        self.assertFalse(result["wink"]["fired"])
        self.assertFalse(result["wink"]["active"])
        self.assertIsNone(result["wink"]["eye"])

    def test_a_yaw_covered_eye_does_not_fire_a_pass(self) -> None:
        result = self.calibrated().update(
            nose=CENTER,
            features=self.eyes(0.11, 0.005, head_turn=0.22),
            tracking_valid=True,
            now=0.0,
        )
        self.assertFalse(result["wink"]["fired"])
        self.assertFalse(result["wink"]["active"])

    def test_a_frontal_wink_still_fires(self) -> None:
        """A small seated tilt is still a wink, not an occluded eye."""

        result = self.calibrated().update(
            nose=CENTER,
            features=self.eyes(0.005, 0.11, head_tilt=8.0, head_turn=0.03),
            tracking_valid=True,
            now=0.0,
        )
        self.assertTrue(result["wink"]["fired"])
        self.assertEqual(result["wink"]["eye"], "left")

    def test_wink_max_tilt_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            ControlThresholds(wink_max_tilt=0.0)


class TrackingLossTests(unittest.TestCase):
    def test_tracking_loss_releases_all_movement_keys(self) -> None:
        state = machine()
        state.update(nose=at(0.2, 0.0), features=NEUTRAL, tracking_valid=True)
        lost = state.update(nose=None, features={}, tracking_valid=False)
        self.assertEqual(lost["keys"], [])
        self.assertFalse(lost["tracking"])
        self.assertTrue(lost["centered"])

    def test_tracking_loss_clears_expression_latches(self) -> None:
        state = machine()
        state.update(nose=CENTER, features={**NEUTRAL, "mouth_opening": 0.2}, tracking_valid=True)
        lost = state.update(nose=None, features={}, tracking_valid=False)
        self.assertFalse(lost["mouth"]["active"])

    def test_expression_refires_after_tracking_is_regained(self) -> None:
        state = machine()
        state.update(nose=CENTER, features={**NEUTRAL, "mouth_opening": 0.2}, tracking_valid=True)
        state.update(nose=None, features={}, tracking_valid=False)
        regained = state.update(nose=CENTER, features={**NEUTRAL, "mouth_opening": 0.2}, tracking_valid=True)
        self.assertTrue(regained["mouth"]["fired"])

    def test_unavailable_feature_does_not_count_as_zero(self) -> None:
        state = machine()
        result = state.update(nose=CENTER, features={}, tracking_valid=True)
        self.assertIsNone(result["mouth"]["value"])
        self.assertFalse(result["mouth"]["active"])


class StateContractTests(unittest.TestCase):
    def test_state_contains_the_documented_contract_keys(self) -> None:
        state = machine().update(nose=CENTER, features=NEUTRAL, tracking_valid=True)
        self.assertLessEqual(
            {"centered", "nose", "direction", "keys", "mouth", "wink", "eyebrow", "tracking"},
            set(state),
        )

    def test_state_reports_whether_it_re_centred_this_frame(self) -> None:
        state = machine().update(nose=CENTER, features=NEUTRAL, tracking_valid=True)
        self.assertIn("recentred", state)

    def test_confidence_is_clamped_to_unit_range(self) -> None:
        """Wink magnitude is what counts, so a strong right wink also reads 1.0."""

        state = machine().update(
            nose=CENTER, features={"mouth_opening": 99.0, "left_wink": -5.0}, tracking_valid=True
        )
        self.assertEqual(state["mouth"]["confidence"], 1.0)
        self.assertEqual(state["wink"]["confidence"], 1.0)

    def test_neutral_eyes_report_no_wink_confidence(self) -> None:
        state = machine().update(
            nose=CENTER, features={"mouth_opening": 0.0, "left_wink": 0.0}, tracking_valid=True
        )
        self.assertEqual(state["wink"]["confidence"], 0.0)

    def test_thresholds_are_publishable_to_the_ui(self) -> None:
        published = ControlThresholds().as_dict()
        self.assertEqual(published["enter_radius"], ControlThresholds().enter_radius)
        self.assertEqual(published["enter_radius"], 0.029)
        self.assertEqual(published["exit_radius"], 0.040)
        self.assertEqual(published["follow_radius"], ControlThresholds().follow_radius)
        self.assertEqual(published["follow_radius"], 0.085)
        self.assertIn("mouth_open", published)
        self.assertIn("brow_on", published)
        self.assertIn("brow_off", published)
        self.assertEqual(published["wink_max_tilt"], 25.0)
        self.assertEqual(published["wink_max_turn"], 0.140)

    def test_hold_labels_include_space_and_l(self) -> None:
        state = machine().update(
            nose=at(0.0, -0.12),
            features={"mouth_opening": 0.2, "left_wink": -0.1},
            tracking_valid=True,
        )
        self.assertEqual(set(hold_labels(state)), {"W", "Space", "L"})


class EyebrowResetTests(unittest.TestCase):
    """Raising the eyebrows recentres pose; an open mouth must not."""

    REST = 0.10
    OPEN_MOUTH = {"mouth_opening": 0.2, "left_wink": 0.0, "eyebrow_raise": 0.10}
    RAISE = {"mouth_opening": 0.0, "left_wink": 0.0, "eyebrow_raise": 0.14}

    def with_rest(self) -> ControlStateMachine:
        state = machine()
        # Existing raise→calibrate cases opt into the restore flag.
        state.eyebrow_recentre = True
        state.update(
            nose=CENTER, features={**NEUTRAL, "eyebrow_raise": self.REST},
            tracking_valid=True, now=-1.0,
        )
        return state

    def test_eyebrow_recentre_is_off_by_default(self) -> None:
        """Temporary: a raise must not call calibrate until the flag is on."""

        self.assertFalse(EYEBROW_RECENTRE)
        state = machine()
        self.assertFalse(state.eyebrow_recentre)
        state.update(
            nose=CENTER, features={**NEUTRAL, "eyebrow_raise": self.REST},
            tracking_valid=True, now=-1.0,
        )
        drifted = at(0.12, 0.0)
        state.update(
            nose=drifted, features={**NEUTRAL, "eyebrow_raise": self.REST},
            tracking_valid=True, now=0.0,
        )
        result = state.update(nose=drifted, features=self.RAISE, tracking_valid=True, now=0.1)
        self.assertFalse(result["eyebrow"]["fired"])
        self.assertFalse(result["centered"])
        self.assertEqual(result["keys"], ["D"])
        self.assertEqual(state.center, CENTER)
        self.assertEqual(state.home, CENTER)

    def test_open_mouth_does_not_recalibrate(self) -> None:
        state = self.with_rest()
        state.update(nose=at(0.12, 0.0), features=self.OPEN_MOUTH, tracking_valid=True, now=0.0)
        result = state.update(
            nose=at(0.12, 0.0), features=self.OPEN_MOUTH, tracking_valid=True, now=0.1
        )
        self.assertFalse(result["eyebrow"]["fired"])
        self.assertFalse(result["centered"])
        self.assertTrue(result["mouth"]["active"])

    def test_eyebrow_raise_calibrates_the_current_nose_as_neutral(self) -> None:
        state = self.with_rest()
        drifted = at(0.12, 0.0)
        state.update(nose=drifted, features={**NEUTRAL, "eyebrow_raise": self.REST}, tracking_valid=True, now=0.0)
        result = state.update(nose=drifted, features=self.RAISE, tracking_valid=True, now=0.1)
        self.assertTrue(result["eyebrow"]["fired"])
        self.assertTrue(result["centered"], "eyebrow raise must recapture neutral like RESET")
        self.assertEqual(result["keys"], [])

    def test_held_raise_does_not_recalibrate_again(self) -> None:
        state = self.with_rest()
        first = state.update(nose=CENTER, features=self.RAISE, tracking_valid=True, now=0.0)
        held = state.update(nose=at(0.12, 0.0), features=self.RAISE, tracking_valid=True, now=0.2)
        self.assertTrue(first["eyebrow"]["fired"])
        self.assertFalse(held["eyebrow"]["fired"])
        self.assertTrue(held["eyebrow"]["active"])
        # Still latched, so a later nose should not keep re-centring.
        self.assertEqual(held["direction"], "E")

    def test_raise_refires_only_after_dropping_below_reset(self) -> None:
        state = self.with_rest()
        state.update(nose=CENTER, features=self.RAISE, tracking_valid=True, now=0.0)
        state.update(nose=CENTER, features=self.OPEN_MOUTH, tracking_valid=True, now=0.2)
        again = state.update(nose=at(0.12, 0.0), features=self.RAISE, tracking_valid=True, now=0.4)
        self.assertTrue(again["eyebrow"]["fired"])
        self.assertTrue(again["centered"])

    def test_open_mouth_still_holds_shoot_while_brows_are_resting(self) -> None:
        state = self.with_rest()
        result = state.update(nose=CENTER, features=self.OPEN_MOUTH, tracking_valid=True, now=0.0)
        self.assertTrue(result["mouth"]["active"])
        self.assertIn("Space", hold_labels(result))
        self.assertFalse(result["eyebrow"]["fired"])

    def test_eyebrow_raise_does_not_raise_mouth_rest_thresholds(self) -> None:
        state = self.with_rest()
        before = state.mouth_thresholds
        state.update(nose=CENTER, features=self.RAISE, tracking_valid=True, now=0.0)
        self.assertEqual(state.mouth_thresholds, before)

    def test_missing_eyebrow_feature_does_not_reset(self) -> None:
        state = self.with_rest()
        result = state.update(
            nose=at(0.12, 0.0),
            features={"mouth_opening": 0.2, "left_wink": 0.0},
            tracking_valid=True,
            now=0.0,
        )
        self.assertFalse(result["eyebrow"]["fired"])
        self.assertFalse(result["centered"])

    def test_first_frame_samples_rest_and_does_not_fire(self) -> None:
        """A face that arrives already raised must not reset on sight."""

        state = machine()
        result = state.update(nose=CENTER, features=self.RAISE, tracking_valid=True, now=0.0)
        self.assertFalse(result["eyebrow"]["fired"])
        self.assertAlmostEqual(state.brow_rest or 0.0, self.RAISE["eyebrow_raise"])

    def test_gesture_reset_does_not_resample_brow_rest(self) -> None:
        state = self.with_rest()
        before = state.brow_rest
        state.update(nose=CENTER, features=self.RAISE, tracking_valid=True, now=0.0)
        self.assertEqual(state.brow_rest, before)

    def test_click_calibrate_resamples_brow_rest(self) -> None:
        state = self.with_rest()
        state.calibrate(CENTER, brow_rest=0.08)
        # 0.10 was a raise against the old rest; against 0.08 it is still a
        # raise, but 0.10 is only +0.02, below brow_on=0.030.
        result = state.update(
            nose=CENTER,
            features={"mouth_opening": 0.0, "left_wink": 0.0, "eyebrow_raise": 0.10},
            tracking_valid=True,
            now=0.0,
        )
        self.assertFalse(result["eyebrow"]["fired"])
        high = state.update(
            nose=CENTER,
            features={"mouth_opening": 0.0, "left_wink": 0.0, "eyebrow_raise": 0.12},
            tracking_valid=True,
            now=0.1,
        )
        self.assertTrue(high["eyebrow"]["fired"])


class ChannelViewTests(unittest.TestCase):
    """The generic per-channel view, added so a drill can watch any channel."""

    def _fired(self) -> dict[str, object]:
        state = machine()
        return state.update(
            nose=CENTER,
            features={"mouth_opening": 0.2, "left_wink": 0.1, "left_eye_opening": 0.1, "right_eye_opening": 0.1},
            tracking_valid=True,
        )

    def test_state_carries_one_entry_per_registered_channel(self) -> None:
        channels = self._fired()["channels"]
        self.assertEqual(set(channels), set(CHANNELS))

    def test_channel_view_and_legacy_key_report_the_same_values(self) -> None:
        """Phase 2 has not run, so the old keys must still be exact."""

        state = self._fired()
        for channel_name, legacy_key in LEGACY_CHANNEL_KEYS.items():
            with self.subTest(channel=channel_name):
                self.assertEqual(state[legacy_key], state["channels"][channel_name])

    def test_legacy_mouth_key_still_reports_the_shoot_gesture(self) -> None:
        state = self._fired()
        self.assertTrue(state["mouth"]["fired"])
        self.assertTrue(state["channels"]["mouth_open"]["fired"])

    def test_legacy_wink_key_keeps_carrying_which_eye_winked(self) -> None:
        state = self._fired()
        self.assertEqual(state["wink"]["eye"], state["channels"]["wink"]["eye"])

    def test_losing_tracking_clears_every_channel(self) -> None:
        state = machine()
        self._fired()
        lost = state.update(nose=None, features={}, tracking_valid=False)
        for view in lost["channels"].values():
            self.assertFalse(view["active"])
            self.assertFalse(view["fired"])

    def test_state_publishes_the_map_it_was_computed_under(self) -> None:
        self.assertEqual(self._fired()["bindings"], default_bindings().as_dict())

    def test_machine_defaults_to_the_shipped_bindings(self) -> None:
        self.assertEqual(ControlStateMachine().bindings.as_dict(), default_bindings().as_dict())

    def test_rebinding_is_reflected_in_the_published_map(self) -> None:
        state = ControlStateMachine(bindings=default_bindings().rebound("SHOOT", "wink"))
        state.calibrate(CENTER)
        published = state.update(nose=CENTER, features=NEUTRAL, tracking_valid=True)["bindings"]
        self.assertEqual(published, {"SHOOT": "wink"})

    def test_rebinding_does_not_change_which_channels_are_measured(self) -> None:
        """Detection is binding-independent: a drill watches unbound channels."""

        state = ControlStateMachine(bindings=default_bindings().rebound("SHOOT", "wink"))
        state.calibrate(CENTER)
        result = state.update(
            nose=CENTER, features={**NEUTRAL, "mouth_opening": 0.2}, tracking_valid=True
        )
        self.assertTrue(result["channels"]["mouth_open"]["fired"])


class FollowDeadzoneTests(unittest.TestCase):
    """Two-radius follow: outer ring drags; the band inside it holds WASD."""

    # Beyond follow_radius (0.085) so the first update must slide the center.
    FAR_EAST = at(0.28, 0.0)

    def follow_machine(self) -> ControlStateMachine:
        state = machine()
        state.set_deadzone_mode("follow")
        return state

    def test_default_mode_is_fixed_center(self) -> None:
        state = machine()
        self.assertEqual(state.deadzone_mode, "fixed")
        result = state.update(nose=CENTER, features=NEUTRAL, tracking_valid=True)
        self.assertEqual(result["deadzone_mode"], "fixed")

    def test_parse_rejects_unknown_modes(self) -> None:
        with self.assertRaises(ValueError):
            parse_deadzone_mode("sticky")

    def test_fixed_mode_still_requires_return_to_the_calibrated_center(self) -> None:
        state = machine()
        state.update(nose=self.FAR_EAST, features=NEUTRAL, tracking_valid=True)
        # Halfway back from a far look is still well outside the original zone.
        halfway = at(0.10, 0.0)
        result = state.update(nose=halfway, features=NEUTRAL, tracking_valid=True)
        self.assertEqual(result["keys"], ["D"])
        self.assertFalse(result["centered"])

    def test_follow_does_not_drag_inside_the_outer_ring(self) -> None:
        state = self.follow_machine()
        # Past the deadzone, short of the outer follow ring (0.085).
        mid = at(0.06, 0.0)
        result = state.update(nose=mid, features=NEUTRAL, tracking_valid=True)
        self.assertEqual(result["keys"], ["D"])
        self.assertEqual(state.center, CENTER)
        self.assertAlmostEqual(result["nose"]["x"], 0.06, places=3)

    def test_follow_holds_wasd_after_a_small_move_back_from_the_outer_ring(self) -> None:
        state = self.follow_machine()
        moving = state.update(nose=self.FAR_EAST, features=NEUTRAL, tracking_valid=True)
        self.assertEqual(moving["keys"], ["D"])
        self.assertFalse(moving["centered"])
        self.assertNotEqual(state.center, CENTER)
        self.assertEqual(state.home, CENTER)

        # Still between the inner deadzone and the outer ring.
        slight_back = at(0.28 - 0.04, 0.0)
        result = state.update(nose=slight_back, features=NEUTRAL, tracking_valid=True)
        self.assertEqual(result["keys"], ["D"])
        self.assertFalse(result["centered"])

    def test_follow_releases_only_inside_the_inner_deadzone(self) -> None:
        state = self.follow_machine()
        state.update(nose=self.FAR_EAST, features=NEUTRAL, tracking_valid=True)
        # After drag, center sits follow_radius behind the nose.
        inside = (
            state.center[0] + 0.02,
            state.center[1],
        )
        result = state.update(nose=inside, features=NEUTRAL, tracking_valid=True)
        self.assertEqual(result["keys"], [])
        self.assertTrue(result["centered"])
        self.assertEqual(state.home, CENTER)

    def test_same_small_move_does_not_release_in_fixed_mode(self) -> None:
        state = machine()
        state.update(nose=self.FAR_EAST, features=NEUTRAL, tracking_valid=True)
        slight_back = at(0.28 - 0.04, 0.0)
        result = state.update(nose=slight_back, features=NEUTRAL, tracking_valid=True)
        self.assertEqual(result["keys"], ["D"])
        self.assertFalse(result["centered"])

    def test_follow_pins_the_nose_to_the_outer_circle(self) -> None:
        state = self.follow_machine()
        state.update(nose=self.FAR_EAST, features=NEUTRAL, tracking_valid=True)
        held = state.update(nose=self.FAR_EAST, features=NEUTRAL, tracking_valid=True)
        self.assertEqual(held["keys"], ["D"])
        self.assertAlmostEqual(held["nose"]["x"], state.thresholds.follow_radius, places=3)

    def test_held_look_in_follow_does_not_auto_recalibrate(self) -> None:
        """A still D hold must stay in D; do not snap home onto the nose."""

        state = self.follow_machine()
        first = state.update(
            nose=self.FAR_EAST, features=NEUTRAL, tracking_valid=True, now=0.0
        )
        self.assertEqual(first["keys"], ["D"])
        dragged = state.center
        # Same pose well past recentre_seconds (3.5). Fixed mode would snap.
        held = state.update(
            nose=self.FAR_EAST, features=NEUTRAL, tracking_valid=True, now=5.0
        )
        self.assertFalse(held["recentred"])
        self.assertEqual(held["keys"], ["D"])
        self.assertFalse(held["centered"])
        self.assertEqual(state.home, CENTER)
        self.assertEqual(state.center, dragged)
        self.assertNotEqual(state.center, self.FAR_EAST)
        self.assertAlmostEqual(
            self.FAR_EAST[0] - state.center[0],
            state.thresholds.follow_radius,
            places=3,
        )

    def test_calibrate_resets_a_followed_deadzone_to_the_new_home(self) -> None:
        state = self.follow_machine()
        state.update(nose=self.FAR_EAST, features=NEUTRAL, tracking_valid=True)
        state.calibrate(self.FAR_EAST)
        result = state.update(nose=self.FAR_EAST, features=NEUTRAL, tracking_valid=True)
        self.assertTrue(result["centered"])
        self.assertEqual(result["keys"], [])
        self.assertEqual(state.center, self.FAR_EAST)
        self.assertEqual(state.home, self.FAR_EAST)

    def test_eyebrow_raise_does_not_recenter_while_disabled(self) -> None:
        state = self.follow_machine()
        rest = {**NEUTRAL, "eyebrow_raise": 0.10}
        state.update(nose=CENTER, features=rest, tracking_valid=True, now=-1.0)
        moving = state.update(nose=self.FAR_EAST, features=rest, tracking_valid=True, now=0.0)
        self.assertEqual(moving["keys"], ["D"])
        dragged = state.center
        raised = {**NEUTRAL, "eyebrow_raise": 0.14}
        result = state.update(nose=self.FAR_EAST, features=raised, tracking_valid=True, now=0.1)
        self.assertFalse(result["eyebrow"]["fired"])
        self.assertEqual(result["keys"], ["D"])
        self.assertEqual(state.center, dragged)
        self.assertEqual(state.home, CENTER)

    def test_eyebrow_reset_clears_follow_drag(self) -> None:
        state = self.follow_machine()
        state.eyebrow_recentre = True
        rest = {**NEUTRAL, "eyebrow_raise": 0.10}
        state.update(nose=CENTER, features=rest, tracking_valid=True, now=-1.0)
        state.update(nose=self.FAR_EAST, features=rest, tracking_valid=True, now=0.0)
        raised = {**NEUTRAL, "eyebrow_raise": 0.14}
        result = state.update(nose=self.FAR_EAST, features=raised, tracking_valid=True, now=0.1)
        self.assertTrue(result["eyebrow"]["fired"])
        self.assertTrue(result["centered"])
        self.assertEqual(state.home, self.FAR_EAST)

    def test_switching_back_to_fixed_snaps_the_zone_to_home(self) -> None:
        state = self.follow_machine()
        state.update(nose=self.FAR_EAST, features=NEUTRAL, tracking_valid=True)
        self.assertNotEqual(state.center, CENTER)
        state.set_deadzone_mode("fixed")
        self.assertEqual(state.deadzone_mode, "fixed")
        self.assertEqual(state.center, CENTER)
        result = state.update(nose=self.FAR_EAST, features=NEUTRAL, tracking_valid=True)
        self.assertEqual(result["keys"], ["D"])
        # Still need to return to the original calibrated zone.
        slight_back = at(0.28 - 0.04, 0.0)
        still = state.update(nose=slight_back, features=NEUTRAL, tracking_valid=True)
        self.assertEqual(still["keys"], ["D"])

    def test_first_frame_records_home_in_follow_mode(self) -> None:
        state = ControlStateMachine()
        state.set_deadzone_mode("follow")
        result = state.update(nose=(0.3, 0.7), features=NEUTRAL, tracking_valid=True)
        self.assertTrue(result["centered"])
        self.assertEqual(state.home, (0.3, 0.7))
        self.assertEqual(state.center, (0.3, 0.7))


if __name__ == "__main__":
    unittest.main()
