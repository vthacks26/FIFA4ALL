import math
import unittest

from tracking.bindings import CHANNELS
from tracking.features import FaceFeatureExtractor, FeatureConfig, Point
from tracking.synthetic import synthetic_sequence


BASE_POINTS = {
    "left_cheek": (0.25, 0.50),
    "right_cheek": (0.75, 0.50),
    "upper_lip": (0.50, 0.58),
    "lower_lip": (0.50, 0.63),
    "nose_tip": (0.50, 0.45),
    "left_eye": (0.38, 0.35),
    "right_eye": (0.62, 0.35),
    "left_upper_eyelid": (0.38, 0.330),
    "left_lower_eyelid": (0.38, 0.370),
    "right_upper_eyelid": (0.62, 0.330),
    "right_lower_eyelid": (0.62, 0.370),
}

# A neutral face carrying the optional landmarks too. Cheeks are 0.50 apart,
# so every "divided by face width" measurement below is just twice the raw
# distance, which keeps the expected values in these tests checkable by hand.
# The mouth is closed here, unlike BASE_POINTS, because these are the points
# the resting-baseline assertions are made against.
RESTING_POINTS: dict[str, Point] = {
    **BASE_POINTS,
    "upper_lip": (0.500, 0.600),
    "lower_lip": (0.500, 0.607),
    # Brow centres 0.092 above the eye corners: 0.184 face widths, the
    # resting brow gap documented for brow_raise.
    "left_brow": (0.380, 0.258),
    "right_brow": (0.620, 0.258),
    # Corners 0.23 apart: 0.46 face widths, the documented resting mouth.
    "left_mouth_corner": (0.385, 0.605),
    "right_mouth_corner": (0.615, 0.605),
    # Chin on the midline, directly below the nose, so the jaw reads zero.
    "chin": (0.500, 0.720),
}


def face(**overrides: Point) -> dict[str, Point]:
    """The resting face with individual landmarks moved."""

    return {**RESTING_POINTS, **overrides}


def rolled(points: dict[str, Point], degrees_clockwise: float) -> dict[str, Point]:
    """Rotate a whole face about the image centre, as a head roll does.

    Rotating every landmark together is what separates a head roll from a
    facial movement: nothing on the face has moved relative to anything else.
    """

    angle = math.radians(degrees_clockwise)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    centre = (0.5, 0.5)
    rotated: dict[str, Point] = {}
    for name, (x, y) in points.items():
        dx, dy = x - centre[0], y - centre[1]
        rotated[name] = (
            centre[0] + dx * cos_a - dy * sin_a,
            centre[1] + dx * sin_a + dy * cos_a,
        )
    return rotated


def measure(points: dict[str, Point]) -> dict[str, float | None]:
    """Unsmoothed feature values for one set of landmarks."""

    extractor = FaceFeatureExtractor(FeatureConfig(smoothing_alpha=1.0))
    frame = extractor.from_named_points(points)
    return {name: feature.value for name, feature in frame.features.items()}


class FaceFeatureExtractorTests(unittest.TestCase):
    def test_extracts_normalized_features_from_controlled_points(self):
        extractor = FaceFeatureExtractor(FeatureConfig(smoothing_alpha=1.0))
        frame = extractor.from_named_points(BASE_POINTS, timestamp_monotonic=10.0)

        self.assertTrue(frame.tracking_valid)
        self.assertAlmostEqual(frame.features["mouth_opening"].value, 0.10)
        self.assertAlmostEqual(frame.features["head_turn"].value, 0.0)
        self.assertAlmostEqual(frame.features["head_tilt"].value, 0.0)
        self.assertAlmostEqual(frame.features["left_wink"].value, 0.0)

    def test_head_turn_sign_uses_camera_image_direction(self):
        extractor = FaceFeatureExtractor(FeatureConfig(smoothing_alpha=1.0))
        points = dict(BASE_POINTS)
        points["nose_tip"] = (0.60, 0.45)

        frame = extractor.from_named_points(points)

        self.assertGreater(frame.features["head_turn"].value, 0.0)

    def test_head_tilt_reports_degrees(self):
        extractor = FaceFeatureExtractor(FeatureConfig(smoothing_alpha=1.0))
        points = dict(BASE_POINTS)
        points["right_eye"] = (0.62, 0.47)

        frame = extractor.from_named_points(points)

        self.assertAlmostEqual(frame.features["head_tilt"].value, math.degrees(math.atan2(0.12, 0.24)))

    def test_left_wink_positive_when_left_eye_is_more_closed(self):
        extractor = FaceFeatureExtractor(FeatureConfig(smoothing_alpha=1.0))
        points = dict(BASE_POINTS)
        points["left_upper_eyelid"] = (0.38, 0.345)
        points["left_lower_eyelid"] = (0.38, 0.355)

        frame = extractor.from_named_points(points)

        self.assertGreater(frame.features["left_wink"].value, 0.0)

    def test_missing_landmark_marks_all_features_unavailable(self):
        extractor = FaceFeatureExtractor()
        points = dict(BASE_POINTS)
        points["nose_tip"] = None

        frame = extractor.from_named_points(points)

        self.assertFalse(frame.tracking_valid)
        self.assertTrue(all(not feature.available for feature in frame.features.values()))
        self.assertIsNone(frame.features["head_turn"].value)

    def test_smoothing_reduces_single_frame_jump(self):
        extractor = FaceFeatureExtractor(FeatureConfig(smoothing_alpha=0.5))
        first = extractor.from_named_points(BASE_POINTS)
        points = dict(BASE_POINTS)
        points["lower_lip"] = (0.50, 0.73)
        second = extractor.from_named_points(points)

        self.assertAlmostEqual(first.features["mouth_opening"].value, 0.10)
        self.assertAlmostEqual(second.features["mouth_opening"].value, 0.20)


class OptionalLandmarkTests(unittest.TestCase):
    def test_core_landmarks_alone_still_produce_a_valid_frame(self):
        frame = FaceFeatureExtractor(FeatureConfig(smoothing_alpha=1.0)).from_named_points(BASE_POINTS)

        self.assertTrue(frame.tracking_valid)
        self.assertAlmostEqual(frame.features["mouth_opening"].value, 0.10)

    def test_missing_brow_landmarks_report_unavailable_not_zero(self):
        frame = FaceFeatureExtractor(FeatureConfig(smoothing_alpha=1.0)).from_named_points(BASE_POINTS)
        brow = frame.features["brow_raise"]

        self.assertFalse(brow.available)
        self.assertIsNone(brow.value)
        self.assertEqual(brow.reason, "missing_landmarks:left_brow,right_brow")

    def test_collapsed_mouth_corners_report_degenerate_geometry(self):
        """A span below the noise floor must not become a huge ratio."""

        values = measure(face(left_mouth_corner=(0.500, 0.605), right_mouth_corner=(0.501, 0.605)))
        frame = FaceFeatureExtractor(FeatureConfig(smoothing_alpha=1.0)).from_named_points(
            face(left_mouth_corner=(0.500, 0.605), right_mouth_corner=(0.501, 0.605))
        )

        self.assertIsNone(values["mouth_pucker"])
        self.assertEqual(frame.features["mouth_pucker"].reason, "degenerate_geometry:mouth_pucker")

    def test_optional_feature_forgets_its_smoothing_when_landmarks_disappear(self):
        """A returning measurement must not carry a value from before the gap."""

        extractor = FaceFeatureExtractor(FeatureConfig(smoothing_alpha=0.5))
        extractor.from_named_points(face(left_brow=(0.380, 0.232), right_brow=(0.620, 0.232)))
        extractor.from_named_points(BASE_POINTS)
        recovered = extractor.from_named_points(RESTING_POINTS)

        self.assertAlmostEqual(recovered.features["brow_raise"].value, 0.184)


class BrowRaiseTests(unittest.TestCase):
    def test_resting_brow_gap_is_a_fraction_of_face_width(self):
        self.assertAlmostEqual(measure(RESTING_POINTS)["brow_raise"], 0.184)

    def test_raising_both_brows_increases_the_gap(self):
        raised = measure(face(left_brow=(0.380, 0.232), right_brow=(0.620, 0.232)))

        self.assertAlmostEqual(raised["brow_raise"], 0.236)

    def test_one_raised_brow_counts_as_half_a_raise(self):
        """Averaging per side must not cancel a one-sided raise to zero."""

        single = measure(face(left_brow=(0.380, 0.232)))

        self.assertAlmostEqual(single["brow_raise"], 0.210)

    def test_a_pitched_head_that_fakes_a_brow_raise_moves_the_gate_signal(self):
        """The confound: nodding is the N/S steering axis, not an idle habit.

        A head pitched down lengthens the apparent brow gap past the trigger.
        head_pitch is what the head_level gate reads, so the test that matters
        is that it departs clearly from its resting value at the same moment.
        """

        rest = measure(RESTING_POINTS)
        pitched = measure(
            face(
                left_brow=(0.380, 0.232),
                right_brow=(0.620, 0.232),
                nose_tip=(0.500, 0.480),
            )
        )

        self.assertGreaterEqual(pitched["brow_raise"], CHANNELS["brow_raise"].default_on)
        self.assertAlmostEqual(rest["head_pitch"], 0.20)
        self.assertGreater(abs(pitched["head_pitch"] - rest["head_pitch"]), 0.05)

    def test_head_pitch_falls_when_the_chin_comes_up(self):
        lifted = measure(face(nose_tip=(0.500, 0.420)))

        self.assertLess(lifted["head_pitch"], measure(RESTING_POINTS)["head_pitch"])


class SmileWidthTests(unittest.TestCase):
    def test_resting_mouth_corner_separation_is_a_fraction_of_face_width(self):
        self.assertAlmostEqual(measure(RESTING_POINTS)["mouth_width"], 0.46)

    def test_smiling_widens_the_corner_separation(self):
        smiling = measure(face(left_mouth_corner=(0.365, 0.600), right_mouth_corner=(0.635, 0.600)))

        self.assertGreater(smiling["mouth_width"], 0.53)

    def test_an_open_mouth_narrows_rather_than_widens_the_corners(self):
        """The confound: a yawn is the involuntary version of a smile.

        A jaw drop pulls the corners in, so it can never push mouth_width past
        the smile trigger on its own, and mouth_opening -- what the
        mouth_near_rest gate reads -- rises unmistakably at the same time.
        """

        yawning = measure(
            face(
                lower_lip=(0.500, 0.700),
                left_mouth_corner=(0.390, 0.610),
                right_mouth_corner=(0.610, 0.610),
            )
        )
        rest = measure(RESTING_POINTS)

        self.assertLess(yawning["mouth_width"], rest["mouth_width"])
        self.assertLess(yawning["mouth_width"], CHANNELS["smile_width"].default_off)
        self.assertGreater(yawning["mouth_opening"], rest["mouth_opening"] + 0.05)


class JawLateralTests(unittest.TestCase):
    def test_a_chin_on_the_midline_reads_zero(self):
        self.assertAlmostEqual(measure(RESTING_POINTS)["jaw_lateral"], 0.0)

    def test_sliding_the_chin_toward_image_right_is_positive(self):
        slid = measure(face(chin=(0.525, 0.720)))

        self.assertAlmostEqual(slid["jaw_lateral"], 0.05)

    def test_sliding_the_chin_toward_image_left_is_negative(self):
        slid = measure(face(chin=(0.475, 0.720)))

        self.assertAlmostEqual(slid["jaw_lateral"], -0.05)

    def test_a_rolled_head_does_not_register_as_a_jaw_slide(self):
        """The confound removed by construction, rather than by a gate.

        Rolling the whole face moves the chin a long way in image x while
        nothing on the face has moved relative to anything else. Projecting
        onto the eye line makes the measurement invariant to that.
        """

        rolled_face = rolled(RESTING_POINTS, 15.0)
        values = measure(rolled_face)

        self.assertAlmostEqual(values["jaw_lateral"], 0.0, places=9)
        self.assertAlmostEqual(values["head_tilt"], 15.0, places=9)
        # The naive image-x measurement this replaces would have read far past
        # the trigger on the very same landmarks.
        naive = (rolled_face["chin"][0] - rolled_face["nose_tip"][0]) / 0.5
        self.assertGreater(abs(naive), CHANNELS["jaw_lateral"].default_on)

    def test_a_rolled_jaw_slide_measures_the_same_as_an_unrolled_one(self):
        slid = face(chin=(0.525, 0.720))

        self.assertAlmostEqual(
            measure(rolled(slid, 15.0))["jaw_lateral"],
            measure(slid)["jaw_lateral"],
            places=9,
        )

    def test_a_yaw_that_fakes_a_jaw_slide_moves_the_gate_signal(self):
        """The confound the facing_forward gate exists for.

        The chin sits further from the axis of rotation than the nose tip, so
        a real turn leaves a residual offset that can reach the trigger.
        head_turn moves far more, and well past the steering dead zone.
        """

        turned = measure(face(nose_tip=(0.550, 0.450), chin=(0.580, 0.720)))

        self.assertGreaterEqual(abs(turned["jaw_lateral"]), CHANNELS["jaw_lateral"].default_on)
        self.assertGreater(abs(turned["head_turn"]), 0.062)


class PuckerAndCheekTests(unittest.TestCase):
    def test_a_closed_resting_mouth_reads_near_zero_pucker(self):
        self.assertAlmostEqual(measure(RESTING_POINTS)["mouth_pucker"], 0.007 / 0.23)

    def test_pursing_the_lips_raises_the_aperture_aspect_ratio(self):
        pursed = measure(
            face(
                upper_lip=(0.500, 0.595),
                lower_lip=(0.500, 0.615),
                left_mouth_corner=(0.440, 0.605),
                right_mouth_corner=(0.560, 0.605),
            )
        )

        self.assertGreaterEqual(pursed["mouth_pucker"], CHANNELS["mouth_pucker"].default_on)

    def test_an_open_mouth_raises_pucker_further_than_a_pucker_does(self):
        """Why mouth_pucker ships unselectable: the confound wins outright.

        A jaw drop raises the same ratio by growing the numerator, and it
        raises it harder than a real pucker raises it by shrinking the
        denominator. No threshold ordering separates the two.
        """

        pursed = measure(
            face(
                upper_lip=(0.500, 0.595),
                lower_lip=(0.500, 0.615),
                left_mouth_corner=(0.440, 0.605),
                right_mouth_corner=(0.560, 0.605),
            )
        )
        open_mouth = measure(
            face(
                lower_lip=(0.500, 0.700),
                left_mouth_corner=(0.390, 0.610),
                right_mouth_corner=(0.610, 0.610),
            )
        )

        self.assertGreater(open_mouth["mouth_pucker"], pursed["mouth_pucker"])
        self.assertGreater(open_mouth["mouth_pucker"], CHANNELS["mouth_pucker"].default_on)

    def test_cheek_span_is_normalized_by_the_eye_span_not_by_face_width(self):
        self.assertAlmostEqual(measure(RESTING_POINTS)["cheek_span_ratio"], 0.50 / 0.24)

    def test_a_head_turn_moves_cheek_span_as_much_as_a_puff_would(self):
        """Why cheek_puff ships unselectable: the confound is the same size.

        A puff moves this measurement a percent or two. Yawing the head
        narrows the cheek span by more than that, and nothing in the 2D
        landmarks distinguishes the two.
        """

        rest = measure(RESTING_POINTS)
        # A modest turn: the far cheek foreshortens toward the midline.
        turned = measure(face(left_cheek=(0.280, 0.500), nose_tip=(0.530, 0.450)))
        puff = CHANNELS["cheek_puff"].default_on - rest["cheek_span_ratio"]

        self.assertGreater(abs(turned["cheek_span_ratio"] - rest["cheek_span_ratio"]), abs(puff))


class ChannelThresholdTests(unittest.TestCase):
    """Rest, trigger and release for each channel, on controlled landmarks."""

    def assert_rest_trigger_release(
        self,
        channel_name: str,
        *,
        triggering: dict[str, Point],
        releasing: dict[str, Point],
        magnitude: bool = False,
    ) -> None:
        channel = CHANNELS[channel_name]

        def read(points: dict[str, Point]) -> float:
            value = measure(points)[channel.feature]
            self.assertIsNotNone(value, channel_name)
            return abs(value) if magnitude else value

        self.assertLess(read(RESTING_POINTS), channel.default_off, f"{channel_name} rest")
        self.assertGreaterEqual(read(triggering), channel.default_on, f"{channel_name} trigger")
        self.assertLess(read(releasing), channel.default_off, f"{channel_name} release")

    def test_brow_raise_rests_below_release_triggers_and_releases(self):
        self.assert_rest_trigger_release(
            "brow_raise",
            triggering=face(left_brow=(0.380, 0.232), right_brow=(0.620, 0.232)),
            releasing=face(left_brow=(0.380, 0.250), right_brow=(0.620, 0.250)),
        )

    def test_smile_width_rests_below_release_triggers_and_releases(self):
        self.assert_rest_trigger_release(
            "smile_width",
            triggering=face(
                left_mouth_corner=(0.365, 0.600), right_mouth_corner=(0.635, 0.600)
            ),
            releasing=face(
                left_mouth_corner=(0.3775, 0.603), right_mouth_corner=(0.6225, 0.603)
            ),
        )

    def test_jaw_lateral_rests_below_release_triggers_and_releases(self):
        self.assert_rest_trigger_release(
            "jaw_lateral",
            triggering=face(chin=(0.525, 0.720)),
            releasing=face(chin=(0.507, 0.720)),
            magnitude=True,
        )

    def test_jaw_lateral_triggers_in_either_direction(self):
        channel = CHANNELS["jaw_lateral"]
        left = measure(face(chin=(0.475, 0.720)))["jaw_lateral"]

        self.assertTrue(channel.use_magnitude)
        self.assertGreaterEqual(abs(left), channel.default_on)

    def test_mouth_pucker_rests_below_release_triggers_and_releases(self):
        self.assert_rest_trigger_release(
            "mouth_pucker",
            triggering=face(
                upper_lip=(0.500, 0.595),
                lower_lip=(0.500, 0.615),
                left_mouth_corner=(0.440, 0.605),
                right_mouth_corner=(0.560, 0.605),
            ),
            releasing=face(
                upper_lip=(0.500, 0.599),
                lower_lip=(0.500, 0.611),
                left_mouth_corner=(0.410, 0.605),
                right_mouth_corner=(0.590, 0.605),
            ),
        )

    def test_cheek_puff_rests_below_release_and_triggers(self):
        self.assert_rest_trigger_release(
            "cheek_puff",
            triggering=face(left_cheek=(0.230, 0.500), right_cheek=(0.770, 0.500)),
            releasing=face(left_cheek=(0.2495, 0.500), right_cheek=(0.7505, 0.500)),
        )


class SyntheticSequenceTests(unittest.TestCase):
    def test_all_required_sequences_exist(self):
        for name in [
            "rest",
            "intentional_movement",
            "small_movement",
            "jitter",
            "tracking_loss",
            "recovery",
        ]:
            self.assertGreater(len(synthetic_sequence(name)), 0)

    def test_tracking_loss_uses_unavailable_measurements(self):
        frames = synthetic_sequence("tracking_loss")
        lost = [frame for frame in frames if not frame.tracking_valid]

        self.assertGreater(len(lost), 0)
        self.assertTrue(all(feature.value is None for frame in lost for feature in frame.features.values()))


if __name__ == "__main__":
    unittest.main()
