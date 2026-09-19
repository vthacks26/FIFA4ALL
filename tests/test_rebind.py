"""Tests for adaptive gesture rebinding."""

from __future__ import annotations

import unittest
from typing import Mapping

from tracking.rebind import (
    ASKED_QUIET_Z,
    Baseline,
    Pulse,
    RebindEngine,
    dominant_channel,
)

REST = {
    "mouth_opening": 0.050,
    "left_wink": 0.000,
    "left_eye_opening": 0.100,
    "right_eye_opening": 0.100,
}
# Sigma is deliberately small, as a resting face is fairly still. These give
# roughly 0.001 per standard deviation.
SAMPLES = {name: [value - 0.001, value, value + 0.001] for name, value in REST.items()}


def baseline() -> Baseline:
    return Baseline.from_samples(SAMPLES)


def frames(
    engine: RebindEngine,
    overrides: Mapping[str, float],
    *,
    hold: float = 0.3,
    start: float = 0.0,
    step: float = 1.0 / 30.0,
):
    """Drive one full gesture: rest, hold the override, then rest again."""

    states = []
    now = start
    for _ in range(3):
        states.append(engine.update(dict(REST), now))
        now += step
    held = 0.0
    while held < hold:
        states.append(engine.update({**REST, **overrides}, now))
        now += step
        held += step
    for _ in range(3):
        states.append(engine.update(dict(REST), now))
        now += step
    return states


class BaselineTests(unittest.TestCase):
    def test_z_is_measured_in_this_players_own_standard_deviations(self) -> None:
        base = baseline()
        self.assertAlmostEqual(base.z("mouth_opening", REST["mouth_opening"]), 0.0, places=6)
        self.assertGreater(base.z("mouth_opening", 0.090), 10.0)

    def test_unknown_or_missing_value_is_not_treated_as_resting(self) -> None:
        base = baseline()
        self.assertEqual(base.z("mouth_opening", None), 0.0)
        self.assertEqual(base.z("not_a_feature", 1.0), 0.0)

    def test_requires_enough_rest_samples_to_estimate_spread(self) -> None:
        with self.assertRaises(ValueError):
            Baseline.from_samples({"mouth_opening": [0.05]})

    def test_a_perfectly_still_signal_does_not_produce_infinite_z(self) -> None:
        base = Baseline.from_samples({"mouth_opening": [0.05, 0.05, 0.05]})
        self.assertLess(abs(base.z("mouth_opening", 0.05)), 1e-6)
        self.assertTrue(abs(base.z("mouth_opening", 0.06)) < float("inf"))


class PulseTests(unittest.TestCase):
    def test_three_repetitions_confirm_the_asked_gesture(self) -> None:
        engine = RebindEngine(asked="mouth_open", baseline=baseline())
        outcomes = []
        now = 0.0
        for _ in range(3):
            states = frames(engine, {"mouth_opening": 0.200}, start=now)
            now += len(states) / 30.0
            outcomes.append([s for s in states if s.outcome != "none"][-1].outcome)
        self.assertEqual(outcomes[-1], "confirmed")
        self.assertEqual(engine.update(dict(REST), now).candidate, "mouth_open")

    def test_a_single_long_hold_counts_as_one_repetition(self) -> None:
        engine = RebindEngine(asked="mouth_open", baseline=baseline())
        states = frames(engine, {"mouth_opening": 0.200}, hold=3.0)
        self.assertEqual([s for s in states if s.outcome != "none"][-1].reps, 1)

    def test_a_twitch_too_brief_to_be_deliberate_does_not_count(self) -> None:
        engine = RebindEngine(asked="mouth_open", baseline=baseline())
        states = frames(engine, {"mouth_opening": 0.200}, hold=0.03)
        self.assertTrue(all(state.outcome == "none" for state in states))

    def test_mouth_held_tighter_than_rest_is_not_a_mouth_open_gesture(self) -> None:
        """A negative excursion must not register through abs()."""
        engine = RebindEngine(asked="mouth_open", baseline=baseline())
        states = frames(engine, {"mouth_opening": 0.010})
        self.assertTrue(all(state.outcome == "none" for state in states))

    def test_a_missing_landmark_does_not_read_as_a_resting_value(self) -> None:
        engine = RebindEngine(asked="wink", baseline=baseline())
        state = engine.update({**REST, "left_eye_opening": None}, 0.0)
        self.assertEqual(state.outcome, "none")


class SwitchTests(unittest.TestCase):
    def test_doing_a_different_gesture_switches_the_binding(self) -> None:
        engine = RebindEngine(asked="mouth_open", baseline=baseline())
        states = frames(engine, {"left_wink": 0.060})
        final = [s for s in states if s.outcome != "none"][-1]
        self.assertEqual(final.outcome, "switched")
        self.assertEqual(final.candidate, "wink")
        self.assertEqual(final.switched_from, "mouth_open")

    def test_switching_restarts_the_repetition_count(self) -> None:
        engine = RebindEngine(asked="mouth_open", baseline=baseline())
        now = 0.0
        states = frames(engine, {"mouth_opening": 0.200}, start=now)
        now += len(states) / 30.0
        self.assertEqual([s for s in states if s.outcome != "none"][-1].reps, 1)
        states = frames(engine, {"left_wink": 0.060}, start=now)
        final = [s for s in states if s.outcome != "none"][-1]
        self.assertEqual(final.outcome, "switched")
        self.assertEqual(final.reps, 1)

    def test_a_switched_gesture_must_earn_its_own_three_repetitions(self) -> None:
        engine = RebindEngine(asked="mouth_open", baseline=baseline())
        now = 0.0
        outcomes = []
        for _ in range(3):
            states = frames(engine, {"left_wink": 0.060}, start=now)
            now += len(states) / 30.0
            outcomes.append([s for s in states if s.outcome != "none"][-1].outcome)
        self.assertEqual(outcomes, ["switched", "progress", "confirmed"])


class SpecificityTests(unittest.TestCase):
    """The core guard: a side effect must not steal credit from intent."""

    def _pulse(self, channel: str, context: Mapping[str, float]) -> Pulse:
        return Pulse(
            channel=channel,
            peak_z=context[channel],
            duration_seconds=0.3,
            context=dict(context),
        )

    def test_asked_channel_keeps_credit_when_it_moved_comparably(self) -> None:
        pulse = self._pulse("wink", {"wink": 8.0, "mouth_open": 6.0})
        self.assertEqual(dominant_channel(pulse, "mouth_open"), "mouth_open")

    def test_challenger_wins_only_when_it_dominates_by_the_margin(self) -> None:
        pulse = self._pulse("wink", {"wink": 20.0, "mouth_open": 0.5})
        self.assertEqual(dominant_channel(pulse, "mouth_open"), "wink")

    def test_two_channels_both_far_from_rest_are_treated_as_correlated(self) -> None:
        """Both moved a long way together, so neither can be called intent."""
        pulse = self._pulse("wink", {"wink": 30.0, "mouth_open": ASKED_QUIET_Z + 5.0})
        self.assertIsNone(dominant_channel(pulse, "mouth_open"))

    def test_a_swing_within_resting_noise_is_never_credited(self) -> None:
        pulse = self._pulse("wink", {"wink": 1.0, "mouth_open": 0.1})
        self.assertIsNone(dominant_channel(pulse, "mouth_open"))

    def test_performing_the_asked_gesture_credits_it_directly(self) -> None:
        pulse = self._pulse("mouth_open", {"mouth_open": 12.0, "wink": 0.2})
        self.assertEqual(dominant_channel(pulse, "mouth_open"), "mouth_open")


class ConstructionTests(unittest.TestCase):
    def test_rejects_an_unknown_asked_channel(self) -> None:
        with self.assertRaises(ValueError):
            RebindEngine(asked="eyebrow_wiggle", baseline=baseline())

    def test_rejects_a_repetition_requirement_below_one(self) -> None:
        with self.assertRaises(ValueError):
            RebindEngine(asked="mouth_open", baseline=baseline(), required_reps=0)

    def test_the_asked_channel_is_always_watched_even_if_not_selectable(self) -> None:
        engine = RebindEngine(asked="wink", baseline=baseline(), candidates=("mouth_open",))
        states = frames(engine, {"left_wink": 0.060})
        self.assertTrue(any(s.outcome != "none" for s in states))


if __name__ == "__main__":
    unittest.main()
