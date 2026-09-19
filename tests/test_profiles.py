"""Tests for per-player control profile persistence.

These run with no camera and no ML packages installed, which is the point:
profile loading has to be verifiable in CI.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tracking.bindings import BindingError, BindingMap, default_bindings
from tracking.profiles import (
    SCHEMA_VERSION,
    ChannelThreshold,
    Profile,
    ProfileCorruptError,
    ProfileNameError,
    ProfileNotFoundError,
    ProfileVersionError,
    list_profiles,
    load_profile,
    profile_path,
    save_profile,
    validate_profile_name,
)


def _profile(**overrides: object) -> Profile:
    base: dict[str, object] = dict(
        name="joe",
        display_name="Joe P",
        bindings=default_bindings(),
        mouth_rest=0.064,
        eye_rest=0.101,
        nose_center=(0.51, 0.43),
        channel_thresholds={"mouth_open": ChannelThreshold(on=0.08, off=0.072)},
        saved_at=datetime(2026, 9, 19, 12, 30, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return Profile(**base)  # type: ignore[arg-type]


class ProfileTestCase(unittest.TestCase):
    """Gives each test its own throwaway profile directory."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.directory = Path(self._temp.name) / "profiles"

    def write_raw(self, name: str, payload: object) -> Path:
        """Write a hand-edited file, bypassing save_profile's validation."""

        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{name}.json"
        text = payload if isinstance(payload, str) else json.dumps(payload)
        path.write_text(text, encoding="utf-8")
        return path

    def saved_payload(self, name: str) -> dict:
        return json.loads((self.directory / f"{name}.json").read_text(encoding="utf-8"))


class RoundTripTests(ProfileTestCase):
    def test_saving_then_loading_returns_an_identical_profile(self) -> None:
        original = _profile()
        save_profile(original, directory=self.directory)
        self.assertEqual(load_profile("joe", directory=self.directory), original)

    def test_round_trip_preserves_a_profile_with_no_calibration_measured(self) -> None:
        original = _profile(mouth_rest=None, eye_rest=None, nose_center=None, channel_thresholds={})
        save_profile(original, directory=self.directory)
        loaded = load_profile("joe", directory=self.directory)
        self.assertIsNone(loaded.mouth_rest)
        self.assertIsNone(loaded.eye_rest)
        self.assertIsNone(loaded.nose_center)
        self.assertEqual(loaded.channel_thresholds, {})

    def test_round_trip_preserves_non_default_bindings(self) -> None:
        swapped = BindingMap(bindings={"SHOOT": "wink", "PASS": "mouth_open"})
        save_profile(_profile(bindings=swapped), directory=self.directory)
        loaded = load_profile("joe", directory=self.directory)
        self.assertEqual(loaded.bindings.as_dict(), {"SHOOT": "wink", "PASS": "mouth_open"})

    def test_round_trip_preserves_learned_per_channel_thresholds(self) -> None:
        save_profile(_profile(), directory=self.directory)
        loaded = load_profile("joe", directory=self.directory)
        self.assertEqual(loaded.channel_thresholds["mouth_open"], ChannelThreshold(on=0.08, off=0.072))

    def test_saving_stamps_the_current_time_when_none_is_given(self) -> None:
        before = datetime.now(timezone.utc)
        save_profile(_profile(saved_at=None), directory=self.directory)
        loaded = load_profile("joe", directory=self.directory)
        self.assertIsNotNone(loaded.saved_at)
        self.assertGreaterEqual(loaded.saved_at, before)

    def test_saving_twice_overwrites_rather_than_duplicating(self) -> None:
        save_profile(_profile(display_name="First"), directory=self.directory)
        save_profile(_profile(display_name="Second"), directory=self.directory)
        self.assertEqual(list_profiles(directory=self.directory), ("joe",))
        self.assertEqual(load_profile("joe", directory=self.directory).display_name, "Second")

    def test_saving_leaves_no_temporary_files_behind(self) -> None:
        save_profile(_profile(), directory=self.directory)
        self.assertEqual([p.name for p in self.directory.iterdir()], ["joe.json"])

    def test_saved_file_records_the_current_schema_version(self) -> None:
        save_profile(_profile(), directory=self.directory)
        self.assertEqual(self.saved_payload("joe")["schema_version"], SCHEMA_VERSION)


class DirectoryTests(ProfileTestCase):
    def test_saving_creates_a_missing_profile_directory(self) -> None:
        self.assertFalse(self.directory.exists())
        path = save_profile(_profile(), directory=self.directory)
        self.assertTrue(path.is_file())
        self.assertTrue(self.directory.is_dir())

    def test_saving_creates_missing_parent_directories(self) -> None:
        nested = self.directory / "players" / "local"
        save_profile(_profile(), directory=nested)
        self.assertTrue((nested / "joe.json").is_file())

    def test_listing_a_missing_directory_returns_nothing_rather_than_failing(self) -> None:
        self.assertEqual(list_profiles(directory=self.directory), ())

    def test_listing_returns_saved_names_sorted(self) -> None:
        save_profile(_profile(name="zoe"), directory=self.directory)
        save_profile(_profile(name="amy"), directory=self.directory)
        self.assertEqual(list_profiles(directory=self.directory), ("amy", "zoe"))

    def test_listing_ignores_files_that_are_not_profiles(self) -> None:
        save_profile(_profile(), directory=self.directory)
        (self.directory / "notes.txt").write_text("hello", encoding="utf-8")
        self.assertEqual(list_profiles(directory=self.directory), ("joe",))

    def test_loading_a_profile_that_was_never_saved_says_so(self) -> None:
        with self.assertRaises(ProfileNotFoundError) as caught:
            load_profile("nobody", directory=self.directory)
        self.assertIn("nobody.json", str(caught.exception))


class NameSanitizationTests(ProfileTestCase):
    def test_parent_directory_traversal_is_rejected(self) -> None:
        with self.assertRaises(ProfileNameError):
            profile_path("../../etc/passwd", directory=self.directory)

    def test_a_bare_dot_dot_name_is_rejected(self) -> None:
        with self.assertRaises(ProfileNameError):
            validate_profile_name("..")

    def test_a_nested_path_separator_is_rejected(self) -> None:
        with self.assertRaises(ProfileNameError):
            validate_profile_name("players/joe")

    def test_a_windows_path_separator_is_rejected(self) -> None:
        with self.assertRaises(ProfileNameError):
            validate_profile_name("players\\joe")

    def test_an_absolute_path_is_rejected(self) -> None:
        with self.assertRaises(ProfileNameError):
            validate_profile_name("/etc/passwd")

    def test_a_leading_dot_is_rejected(self) -> None:
        with self.assertRaises(ProfileNameError):
            validate_profile_name(".hidden")

    def test_an_empty_name_is_rejected(self) -> None:
        with self.assertRaises(ProfileNameError):
            validate_profile_name("")

    def test_a_traversing_name_cannot_be_constructed_into_a_profile(self) -> None:
        with self.assertRaises(ProfileNameError):
            _profile(name="../escape")

    def test_loading_a_traversing_name_reads_nothing_outside_the_directory(self) -> None:
        """A planted file one level up must stay unreachable by name."""

        outside = self.directory.parent / "escape.json"
        outside.write_text("{}", encoding="utf-8")
        with self.assertRaises(ProfileNameError):
            load_profile("../escape", directory=self.directory)

    def test_ordinary_names_with_spaces_and_hyphens_are_accepted(self) -> None:
        for name in ("joe", "Joe P", "player-2", "player_2", "a1"):
            self.assertEqual(validate_profile_name(name), name)


class VersionTests(ProfileTestCase):
    def test_a_newer_schema_version_is_rejected_rather_than_read(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        payload["schema_version"] = SCHEMA_VERSION + 1
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileVersionError) as caught:
            load_profile("joe", directory=self.directory)
        message = str(caught.exception)
        self.assertIn("joe.json", message)
        self.assertIn(str(SCHEMA_VERSION + 1), message)

    def test_an_unknown_older_schema_version_is_rejected(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        payload["schema_version"] = 0
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileVersionError):
            load_profile("joe", directory=self.directory)

    def test_a_missing_schema_version_is_corrupt(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        del payload["schema_version"]
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileCorruptError):
            load_profile("joe", directory=self.directory)

    def test_a_non_integer_schema_version_is_corrupt(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        payload["schema_version"] = "1"
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileCorruptError):
            load_profile("joe", directory=self.directory)


class CorruptFileTests(ProfileTestCase):
    def test_unparseable_json_names_the_file_and_the_position(self) -> None:
        self.write_raw("joe", "{not json at all")
        with self.assertRaises(ProfileCorruptError) as caught:
            load_profile("joe", directory=self.directory)
        message = str(caught.exception)
        self.assertIn("joe.json", message)
        self.assertIn("line 1", message)

    def test_a_truncated_file_is_rejected_rather_than_partially_loaded(self) -> None:
        save_profile(_profile(), directory=self.directory)
        path = self.directory / "joe.json"
        path.write_text(path.read_text(encoding="utf-8")[:40], encoding="utf-8")
        with self.assertRaises(ProfileCorruptError):
            load_profile("joe", directory=self.directory)

    def test_a_json_array_instead_of_an_object_is_rejected(self) -> None:
        self.write_raw("joe", [1, 2, 3])
        with self.assertRaises(ProfileCorruptError):
            load_profile("joe", directory=self.directory)

    def test_an_empty_file_is_rejected(self) -> None:
        self.write_raw("joe", "")
        with self.assertRaises(ProfileCorruptError):
            load_profile("joe", directory=self.directory)

    def test_a_missing_display_name_names_the_field(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        del payload["display_name"]
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileCorruptError) as caught:
            load_profile("joe", directory=self.directory)
        self.assertIn("display_name", str(caught.exception))

    def test_a_missing_calibration_field_is_not_defaulted_away(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        del payload["calibration"]["mouth_rest"]
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileCorruptError) as caught:
            load_profile("joe", directory=self.directory)
        self.assertIn("mouth_rest", str(caught.exception))

    def test_an_unknown_field_at_a_known_version_is_rejected(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        payload["deadzone_radius"] = 0.05
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileCorruptError) as caught:
            load_profile("joe", directory=self.directory)
        self.assertIn("deadzone_radius", str(caught.exception))

    def test_a_renamed_file_is_rejected_rather_than_loaded_as_someone_else(self) -> None:
        save_profile(_profile(name="joe"), directory=self.directory)
        (self.directory / "joe.json").rename(self.directory / "amy.json")
        with self.assertRaises(ProfileCorruptError) as caught:
            load_profile("amy", directory=self.directory)
        self.assertIn("joe", str(caught.exception))

    def test_a_non_numeric_calibration_value_is_rejected(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        payload["calibration"]["mouth_rest"] = "quite open"
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileCorruptError):
            load_profile("joe", directory=self.directory)

    def test_a_malformed_nose_centre_is_rejected(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        payload["calibration"]["nose_center"] = [0.5]
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileCorruptError) as caught:
            load_profile("joe", directory=self.directory)
        self.assertIn("nose_center", str(caught.exception))

    def test_an_invalid_timestamp_is_rejected(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        payload["saved_at"] = "last tuesday"
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileCorruptError) as caught:
            load_profile("joe", directory=self.directory)
        self.assertIn("saved_at", str(caught.exception))


class BindingValidationTests(ProfileTestCase):
    def test_an_unknown_channel_is_rejected_with_the_binding_reason(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        payload["bindings"] = {"SHOOT": "eyebrow_wiggle"}
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileCorruptError) as caught:
            load_profile("joe", directory=self.directory)
        message = str(caught.exception)
        self.assertIn("joe.json", message)
        self.assertIn("eyebrow_wiggle", message)
        self.assertIsInstance(caught.exception.__cause__, BindingError)

    def test_an_unknown_action_is_rejected(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        payload["bindings"] = {"DRIBBLE": "wink"}
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileCorruptError) as caught:
            load_profile("joe", directory=self.directory)
        self.assertIn("DRIBBLE", str(caught.exception))

    def test_one_channel_driving_two_actions_is_rejected(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        payload["bindings"] = {"SHOOT": "wink", "PASS": "wink"}
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileCorruptError):
            load_profile("joe", directory=self.directory)

    def test_a_non_string_channel_name_is_rejected(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        payload["bindings"] = {"SHOOT": 7}
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileCorruptError):
            load_profile("joe", directory=self.directory)

    def test_a_threshold_for_an_unknown_channel_is_rejected(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        payload["calibration"]["channel_thresholds"] = {"eyebrow_wiggle": {"on": 0.1, "off": 0.05}}
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileCorruptError) as caught:
            load_profile("joe", directory=self.directory)
        self.assertIn("eyebrow_wiggle", str(caught.exception))

    def test_a_threshold_that_can_never_release_is_rejected(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        payload["calibration"]["channel_thresholds"] = {"mouth_open": {"on": 0.05, "off": 0.09}}
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileCorruptError) as caught:
            load_profile("joe", directory=self.directory)
        self.assertIn("mouth_open", str(caught.exception))

    def test_a_threshold_missing_its_release_value_is_rejected(self) -> None:
        save_profile(_profile(), directory=self.directory)
        payload = self.saved_payload("joe")
        payload["calibration"]["channel_thresholds"] = {"mouth_open": {"on": 0.09}}
        self.write_raw("joe", payload)
        with self.assertRaises(ProfileCorruptError) as caught:
            load_profile("joe", directory=self.directory)
        self.assertIn("off", str(caught.exception))

    def test_constructing_a_profile_with_an_unknown_threshold_channel_raises(self) -> None:
        with self.assertRaises(BindingError):
            _profile(channel_thresholds={"eyebrow_wiggle": ChannelThreshold(on=0.1, off=0.05)})

    def test_a_release_above_the_trigger_is_rejected_at_construction(self) -> None:
        with self.assertRaises(ValueError):
            ChannelThreshold(on=0.05, off=0.09)


class TwoProfileTests(ProfileTestCase):
    def test_two_players_keep_separate_bindings(self) -> None:
        save_profile(_profile(name="joe", bindings=default_bindings()), directory=self.directory)
        save_profile(
            _profile(name="amy", bindings=BindingMap(bindings={"SHOOT": "wink"})),
            directory=self.directory,
        )
        self.assertEqual(
            load_profile("joe", directory=self.directory).bindings.as_dict(),
            {"SHOOT": "mouth_open", "PASS": "wink"},
        )
        self.assertEqual(
            load_profile("amy", directory=self.directory).bindings.as_dict(),
            {"SHOOT": "wink"},
        )


if __name__ == "__main__":
    unittest.main()
