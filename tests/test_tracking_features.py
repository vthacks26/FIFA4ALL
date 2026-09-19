import math
import unittest

from tracking.features import FaceFeatureExtractor, FeatureConfig
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
    "left_inner_brow": (0.40, 0.280),
    "left_outer_brow": (0.32, 0.285),
    "right_inner_brow": (0.60, 0.280),
    "right_outer_brow": (0.68, 0.285),
}


class FaceFeatureExtractorTests(unittest.TestCase):
    def test_extracts_normalized_features_from_controlled_points(self):
        extractor = FaceFeatureExtractor(FeatureConfig(smoothing_alpha=1.0))
        frame = extractor.from_named_points(BASE_POINTS, timestamp_monotonic=10.0)

        self.assertTrue(frame.tracking_valid)
        self.assertAlmostEqual(frame.features["mouth_opening"].value, 0.10)
        self.assertAlmostEqual(frame.features["head_turn"].value, 0.0)
        self.assertAlmostEqual(frame.features["head_tilt"].value, 0.0)
        self.assertAlmostEqual(frame.features["left_wink"].value, 0.0)
        self.assertAlmostEqual(frame.features["eyebrow_raise"].value, 0.095)

    def test_open_mouth_does_not_change_eyebrow_raise(self):
        """Shoot (mouth open) must not look like an eyebrow-raise reset."""

        extractor = FaceFeatureExtractor(FeatureConfig(smoothing_alpha=1.0))
        rest = extractor.from_named_points(BASE_POINTS)
        points = dict(BASE_POINTS)
        points["lower_lip"] = (0.50, 0.68)
        points["upper_lip"] = (0.50, 0.52)

        frame = extractor.from_named_points(points)

        self.assertGreater(frame.features["mouth_opening"].value, 0.15)
        self.assertAlmostEqual(
            frame.features["eyebrow_raise"].value,
            rest.features["eyebrow_raise"].value,
        )

    def test_raised_brows_increase_eyebrow_raise(self):
        extractor = FaceFeatureExtractor(FeatureConfig(smoothing_alpha=1.0))
        rest = extractor.from_named_points(BASE_POINTS)
        points = dict(BASE_POINTS)
        points["left_inner_brow"] = (0.40, 0.250)
        points["left_outer_brow"] = (0.32, 0.255)
        points["right_inner_brow"] = (0.60, 0.250)
        points["right_outer_brow"] = (0.68, 0.255)

        frame = extractor.from_named_points(points)

        self.assertGreater(
            frame.features["eyebrow_raise"].value - rest.features["eyebrow_raise"].value,
            0.030,
        )

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
