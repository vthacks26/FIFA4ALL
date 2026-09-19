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


class SelectableChannelTests(unittest.TestCase):
    def test_selectable_channels_are_stable_and_registered(self) -> None:
        names = [c.name for c in selectable_channels()]
        self.assertEqual(names, [c.name for c in selectable_channels()])
        for name in names:
            self.assertIn(name, CHANNELS)


if __name__ == "__main__":
    unittest.main()
