import unittest

from tracking.control_preview import PreviewThresholds, suggested_keys
from tracking.mac_camera import CameraDevice, name_is_phone, select_builtin_mac_camera
from tracking.quartz_keys import HeldKeySession, RecordingKeyInjector, labels_to_keys


class SuggestedKeysTests(unittest.TestCase):
    def setUp(self) -> None:
        self.th = PreviewThresholds()
        self.closed = {"mouth_opening": 0.02, "left_wink": 0.0}

    def test_neutral_is_empty(self):
        self.assertEqual(suggested_keys(self.closed, self.th, (0.0, 0.0)), [])

    def test_nose_left_is_d_and_right_is_a(self):
        self.assertEqual(suggested_keys(self.closed, self.th, (-0.08, 0.0)), ["D"])
        self.assertEqual(suggested_keys(self.closed, self.th, (0.08, 0.0)), ["A"])

    def test_nose_up_is_w_and_down_is_s(self):
        self.assertEqual(suggested_keys(self.closed, self.th, (0.0, -0.08)), ["W"])
        self.assertEqual(suggested_keys(self.closed, self.th, (0.0, 0.08)), ["S"])

    def test_mouth_open_holds_space(self):
        keys = suggested_keys({"mouth_opening": 0.12, "left_wink": 0.0}, self.th, (0.0, 0.0))
        self.assertEqual(keys, ["Space"])

    def test_wink_holds_l(self):
        keys = suggested_keys({"mouth_opening": 0.02, "left_wink": 0.04}, self.th, (0.0, 0.0))
        self.assertEqual(keys, ["L"])


class QuartzGlueTests(unittest.TestCase):
    def test_labels_map_to_hold_session(self):
        inj = RecordingKeyInjector(clock=lambda: 0.0)
        session = HeldKeySession(inj)
        session.apply(labels_to_keys(["D", "Space"]))
        self.assertEqual(session.held(), frozenset({"d", "space"}))
        session.apply(frozenset())
        downs = [e.key for e in inj.events if e.action == "down"]
        ups = [e.key for e in inj.events if e.action == "up"]
        self.assertEqual(set(downs), {"d", "space"})
        self.assertEqual(set(ups), {"d", "space"})


class MacCameraTests(unittest.TestCase):
    def test_selects_macbook_over_iphone(self):
        devices = [
            CameraDevice(0, "iPhone Camera", is_continuity=True),
            CameraDevice(1, "MacBook Pro Camera"),
        ]
        chosen = select_builtin_mac_camera(devices)
        self.assertEqual(chosen.index, 1)

    def test_refuses_iphone_only(self):
        with self.assertRaises(RuntimeError):
            select_builtin_mac_camera(
                [CameraDevice(0, "iPhone (33) Camera", is_continuity=True)]
            )

    def test_phone_markers(self):
        self.assertTrue(name_is_phone("iPhone Camera", False))
        self.assertFalse(name_is_phone("MacBook Pro Camera", False))


class AnnotateFrameTests(unittest.TestCase):
    def test_annotate_blank_frame_keeps_shape(self):
        import numpy as np

        from tracking.control_preview import NoseJoystickState
        from tracking.live import annotate_frame

        blank = np.zeros((120, 160, 3), dtype=np.uint8)
        vis = annotate_frame(
            blank,
            landmarks=None,
            joystick=NoseJoystickState(),
            thresholds=PreviewThresholds(),
            labels=["W", "A"],
            tracking_valid=False,
            space_hold_seconds=0.0,
        )
        self.assertEqual(vis.shape, blank.shape)


if __name__ == "__main__":
    unittest.main()
