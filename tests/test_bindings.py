"""Tests for action-to-gesture bindings."""

from __future__ import annotations

import unittest

from tracking.bindings import (
    ACTIONS,
    CHANNELS,
    BindingError,
    BindingMap,
    GestureChannel,
    default_bindings,
    selectable_channels,
)
from tracking.frames import FEATURE_DOCUMENTATION, FEATURE_UNITS


class DefaultBindingTests(unittest.TestCase):
    def test_default_map_reproduces_shipped_mapping(self) -> None:
        self.assertEqual(default_bindings().as_dict(), {"SHOOT": "mouth_open", "PASS": "wink"})

    def test_shoot_holds_its_key_and_pass_taps(self) -> None:
        self.assertEqual(ACTIONS["SHOOT"].trigger, "hold")
        self.assertEqual(ACTIONS["PASS"].trigger, "tap")

    def test_default_channels_match_shipped_thresholds(self) -> None:
        self.assertEqual(CHANNELS["mouth_open"].default_on, 0.090)
        self.assertEqual(CHANNELS["mouth_open"].default_off, 0.060)
        self.assertEqual(CHANNELS["wink"].default_on, 0.025)
        self.assertEqual(CHANNELS["wink"].default_off, 0.015)

    def test_wink_reads_magnitude_so_either_eye_fires(self) -> None:
        self.assertTrue(CHANNELS["wink"].use_magnitude)

    def test_wink_keeps_its_blink_gate(self) -> None:
        self.assertEqual(CHANNELS["wink"].gate, "one_eye_open")


class BindingMapTests(unittest.TestCase):
    def test_rejects_unknown_action(self) -> None:
        with self.assertRaises(BindingError):
            BindingMap(bindings={"DRIBBLE": "mouth_open"})

    def test_rejects_unknown_channel(self) -> None:
        with self.assertRaises(BindingError):
            BindingMap(bindings={"SHOOT": "eyebrow_wiggle"})

    def test_rejects_one_channel_driving_two_actions(self) -> None:
        with self.assertRaises(BindingError):
            BindingMap(bindings={"SHOOT": "wink", "PASS": "wink"})

    def test_lookup_by_action_and_by_channel(self) -> None:
        binding = default_bindings()
        self.assertEqual(binding.channel_for("SHOOT").name, "mouth_open")
        self.assertEqual(binding.action_for("wink").name, "PASS")
        self.assertIsNone(binding.action_for("nothing_bound_here"))

    def test_rebinding_leaves_the_displaced_action_unbound(self) -> None:
        rebound = default_bindings().rebound("SHOOT", "wink")
        self.assertEqual(rebound.bindings["SHOOT"], "wink")
        self.assertNotIn("PASS", rebound.bindings)

    def test_rebinding_does_not_mutate_the_original(self) -> None:
        binding = default_bindings()
        binding.rebound("SHOOT", "wink")
        self.assertEqual(binding.bindings["SHOOT"], "mouth_open")


class ChannelValidationTests(unittest.TestCase):
    def _channel(self, **overrides: object) -> GestureChannel:
        base = dict(
            name="test",
            label="Test",
            feature="mouth_opening",
            required_features=("mouth_opening",),
            default_on=0.1,
            default_off=0.05,
        )
        base.update(overrides)
        return GestureChannel(**base)  # type: ignore[arg-type]

    def test_release_threshold_must_sit_below_trigger(self) -> None:
        with self.assertRaises(ValueError):
            self._channel(default_off=0.2)

    def test_channel_must_require_the_feature_it_reads(self) -> None:
        with self.assertRaises(ValueError):
            self._channel(required_features=("something_else",))

    def test_every_registered_channel_declares_its_dependencies(self) -> None:
        for channel in CHANNELS.values():
            self.assertIn(channel.feature, channel.required_features, channel.name)

    def test_gated_channels_declare_a_resting_baseline(self) -> None:
        """The eligibility rule: a confound gate needs a per-user reference."""
        for channel in CHANNELS.values():
            if channel.gate is not None:
                self.assertIsNotNone(channel.rest_feature, channel.name)


class ChannelVocabularyTests(unittest.TestCase):
    """Phase 3: the movements a player can choose between."""

    def test_every_channel_reads_features_the_extractor_publishes(self) -> None:
        for channel in CHANNELS.values():
            for feature in channel.required_features:
                self.assertIn(feature, FEATURE_UNITS, f"{channel.name} -> {feature}")

    def test_every_channel_documents_its_features(self) -> None:
        for channel in CHANNELS.values():
            self.assertIn(channel.feature, FEATURE_DOCUMENTATION, channel.name)

    def test_every_channel_samples_a_resting_value_for_this_user(self) -> None:
        """Eligibility rule 1: no hardcoded resting constant."""
        for channel in CHANNELS.values():
            self.assertIsNotNone(channel.rest_feature, channel.name)

    def test_every_channel_has_a_hysteresis_pair(self) -> None:
        """Eligibility rule 2: trigger high, release low."""
        for channel in CHANNELS.values():
            self.assertLess(channel.default_off, channel.default_on, channel.name)

    def test_brow_raise_is_gated_on_the_head_staying_level(self) -> None:
        channel = CHANNELS["brow_raise"]

        self.assertEqual(channel.gate, "head_level")
        self.assertIn("head_pitch", channel.required_features)
        self.assertTrue(channel.selectable)

    def test_smile_width_is_gated_on_the_mouth_staying_near_rest(self) -> None:
        channel = CHANNELS["smile_width"]

        self.assertEqual(channel.gate, "mouth_near_rest")
        self.assertIn("mouth_opening", channel.required_features)
        self.assertTrue(channel.selectable)

    def test_jaw_lateral_is_gated_on_facing_forward(self) -> None:
        channel = CHANNELS["jaw_lateral"]

        self.assertEqual(channel.gate, "facing_forward")
        self.assertIn("head_turn", channel.required_features)
        self.assertTrue(channel.use_magnitude)
        self.assertTrue(channel.selectable)

    def test_cheek_puff_is_not_offered_because_yaw_swamps_it(self) -> None:
        self.assertFalse(CHANNELS["cheek_puff"].selectable)

    def test_mouth_pucker_is_not_offered_because_it_co_fires_with_shoot(self) -> None:
        channel = CHANNELS["mouth_pucker"]

        self.assertFalse(channel.selectable)
        # It declares the channels it collides with so Phase 4 scoring can see
        # the co-fire rather than having to rediscover it.
        self.assertIn("mouth_opening", channel.required_features)
        self.assertIn("mouth_width", channel.required_features)

    def test_an_ungated_channel_is_never_offered_alongside_a_gated_one(self) -> None:
        """Eligibility rule 3, as far as the registry can enforce it.

        mouth_open is the exception this cannot cover: it predates the rule
        and has no involuntary confound of its own, so it is named here rather
        than quietly excluded.
        """

        for channel in selectable_channels():
            if channel.name == "mouth_open":
                continue
            self.assertIsNotNone(channel.gate, channel.name)
            # A gate needs something to read besides the channel's own signal.
            self.assertGreater(len(channel.required_features), 1, channel.name)


class SelectableChannelTests(unittest.TestCase):
    def test_selectable_channels_are_stable_and_registered(self) -> None:
        names = [c.name for c in selectable_channels()]
        self.assertEqual(names, [c.name for c in selectable_channels()])
        for name in names:
            self.assertIn(name, CHANNELS)

    def test_players_are_offered_the_phase_three_gestures(self) -> None:
        names = [c.name for c in selectable_channels()]

        self.assertEqual(
            names,
            ["mouth_open", "wink", "brow_raise", "smile_width", "jaw_lateral"],
        )


if __name__ == "__main__":
    unittest.main()
