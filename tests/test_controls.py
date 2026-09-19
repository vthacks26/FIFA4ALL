"""Tests for the shared control state derivation."""

from __future__ import annotations

import unittest

from tracking.controls import (
    CARDINALS,
    DIRECTION_KEYS,
    ControlStateMachine,
    ControlThresholds,
    classify_direction,
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

    def test_mouth_reset_must_be_below_open(self) -> None:
        with self.assertRaises(ValueError):
            ControlThresholds(mouth_open=0.09, mouth_reset=0.09)

    def test_wink_off_must_be_below_wink_on(self) -> None:
        with self.assertRaises(ValueError):
            ControlThresholds(wink_on=0.02, wink_off=0.03)


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


class WinkEdgeTriggerTests(unittest.TestCase):
    def test_wink_fires_once_per_activation(self) -> None:
        state = machine()
        first = state.update(nose=CENTER, features={**NEUTRAL, "left_wink": 0.1}, tracking_valid=True)
        held = state.update(nose=CENTER, features={**NEUTRAL, "left_wink": 0.1}, tracking_valid=True)
        self.assertTrue(first["wink"]["fired"])
        self.assertFalse(held["wink"]["fired"], "eye held closed must not repeat the pass action")


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
    def test_state_matches_the_documented_contract_keys(self) -> None:
        state = machine().update(nose=CENTER, features=NEUTRAL, tracking_valid=True)
        self.assertEqual(
            set(state),
            {"centered", "nose", "direction", "keys", "mouth", "wink", "tracking"},
        )

    def test_confidence_is_clamped_to_unit_range(self) -> None:
        state = machine().update(
            nose=CENTER, features={"mouth_opening": 99.0, "left_wink": -5.0}, tracking_valid=True
        )
        self.assertEqual(state["mouth"]["confidence"], 1.0)
        self.assertEqual(state["wink"]["confidence"], 0.0)

    def test_thresholds_are_publishable_to_the_ui(self) -> None:
        published = ControlThresholds().as_dict()
        self.assertEqual(published["enter_radius"], ControlThresholds().enter_radius)
        self.assertIn("mouth_open", published)


if __name__ == "__main__":
    unittest.main()
