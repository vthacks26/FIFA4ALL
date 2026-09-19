import unittest

from tracking.control_preview import HoldState, NoseJoystickState, PreviewThresholds, suggested_keys
from tracking.live import hit_reset_button, recalibrate_pose, reset_button_rect
from tracking.mac_camera import (
    CameraDevice,
    allowed_opencv_indexes,
    name_is_phone,
    refuse_if_phone,
    resolve_mac_camera,
    select_builtin_mac_camera,
)
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

    def test_skips_opencv_index_zero_when_phone(self):
        devices = [
            CameraDevice(0, "iPhone (33) Camera", is_continuity=True),
            CameraDevice(1, "MacBook Pro Camera", unique_id="mac-id"),
        ]
        self.assertEqual(allowed_opencv_indexes(devices), [1])
        chosen = resolve_mac_camera(camera_index=0, devices=devices)
        self.assertEqual(chosen.index, 1)
        self.assertEqual(chosen.name, "MacBook Pro Camera")

    def test_keeps_macbook_at_index_zero(self):
        devices = [CameraDevice(0, "MacBook Pro Camera", unique_id="mac-id")]
        self.assertEqual(allowed_opencv_indexes(devices), [0])
        chosen = resolve_mac_camera(camera_index=0, devices=devices)
        self.assertEqual(chosen.index, 0)

    def test_resolve_by_unique_id_skips_phone(self):
        devices = [
            CameraDevice(0, "iPhone Camera", unique_id="phone-id", is_continuity=True),
            CameraDevice(1, "FaceTime HD Camera", unique_id="face-id"),
        ]
        chosen = resolve_mac_camera(camera_unique_id="face-id", devices=devices)
        self.assertEqual(chosen.name, "FaceTime HD Camera")
        with self.assertRaises(RuntimeError):
            resolve_mac_camera(camera_unique_id="phone-id", devices=devices)
        with self.assertRaises(RuntimeError):
            refuse_if_phone(devices[0])


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
            camera_name="MacBook Pro Camera",
        )
        self.assertEqual(vis.shape, blank.shape)


class ResetButtonTests(unittest.TestCase):
    def test_reset_hit_box_is_bottom_right(self):
        x1, y1, x2, y2 = reset_button_rect(640, 360)
        self.assertGreater(x1, 400)
        self.assertGreater(y1, 280)
        self.assertTrue(hit_reset_button(x1 + 8, y1 + 8, 640, 360))
        self.assertFalse(hit_reset_button(10, 10, 640, 360))

    def test_recalibrate_clears_joystick_center(self):
        joystick = NoseJoystickState()
        joystick.update((0.4, 0.4))
        self.assertIsNotNone(joystick.center)
        space = HoldState()
        space.update(True, 1.0)
        session = HeldKeySession(RecordingKeyInjector(clock=lambda: 0.0))
        session.apply(labels_to_keys(["W"]))
        recalibrate_pose(joystick, space, session)
        self.assertIsNone(joystick.center)
        self.assertIsNone(space.started_at)
        self.assertEqual(session.held(), frozenset())


if __name__ == "__main__":
    unittest.main()
