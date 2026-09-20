"""Hand gestures, palm look-axis, and auto-swap with face controls."""

from __future__ import annotations

import unittest

from output.keyboard import RecordingKeyboard
from output.session import (
    PASS_PRESS_DELAY_SECONDS,
    SHOOT_PRESS_DELAY_SECONDS,
    InputSession,
)
from tracking.controls import ControlStateMachine, hold_labels
from tracking.hands import (
    AutoSwapRouter,
    GESTURE_ON,
    HAND_ENTER_FRAMES,
    HAND_EXIT_FRAMES,
    classify_gesture,
    fingers_up,
    gesture_features,
    hand_is_clear,
    landmark_points,
    mirror_points,
    palm_center,
    palm_span,
)

CENTER = (0.50, 0.50)
FACE_NEUTRAL = {"mouth_opening": 0.0, "left_wink": 0.0}
FACE_SHOOT = {"mouth_opening": 0.20, "left_wink": 0.0}


def _hand(
    *,
    up: frozenset[str] | set[str],
    origin: tuple[float, float] = (0.52, 0.72),
    scale: float = 0.22,
    thumb_out: bool | None = None,
) -> list[tuple[float, float]]:
    """Build a 21-point MediaPipe-style hand in normalized image space."""

    raised = frozenset(up)
    pts: list[tuple[float, float]] = [(0.0, 0.0)] * 21
    pts[0] = origin
    mcp_y = origin[1] - 0.32 * scale
    pts[5] = (origin[0] - 0.16 * scale, mcp_y)
    pts[9] = (origin[0] - 0.02 * scale, mcp_y - 0.02 * scale)
    pts[13] = (origin[0] + 0.12 * scale, mcp_y)
    pts[17] = (origin[0] + 0.26 * scale, mcp_y + 0.02 * scale)

    pts[1] = (origin[0] - 0.10 * scale, origin[1] - 0.08 * scale)
    pts[2] = (origin[0] - 0.18 * scale, origin[1] - 0.16 * scale)
    thumb_extended = thumb_out if thumb_out is not None else ("thumb" in raised)
    if thumb_extended:
        pts[3] = (origin[0] - 0.32 * scale, origin[1] - 0.26 * scale)
        pts[4] = (origin[0] - 0.46 * scale, origin[1] - 0.36 * scale)
    else:
        pts[3] = (origin[0] - 0.06 * scale, origin[1] - 0.16 * scale)
        pts[4] = (origin[0] + 0.02 * scale, origin[1] - 0.20 * scale)

    chains = (
        ("index", 5, 6, 7, 8),
        ("middle", 9, 10, 11, 12),
        ("ring", 13, 14, 15, 16),
        ("pinky", 17, 18, 19, 20),
    )
    for name, mcp_i, pip_i, dip_i, tip_i in chains:
        mcp = pts[mcp_i]
        if name in raised:
            pts[pip_i] = (mcp[0], mcp[1] - 0.28 * scale)
            pts[dip_i] = (mcp[0], mcp[1] - 0.42 * scale)
            pts[tip_i] = (mcp[0], mcp[1] - 0.60 * scale)
        else:
            pts[pip_i] = (mcp[0] + 0.01 * scale, mcp[1] + 0.08 * scale)
            pts[dip_i] = (mcp[0] + 0.01 * scale, mcp[1] + 0.14 * scale)
            pts[tip_i] = (mcp[0] + 0.01 * scale, mcp[1] + 0.20 * scale)
    return pts


def peace() -> list[tuple[float, float]]:
    return _hand(up={"index", "middle"}, thumb_out=False)


def open_palm() -> list[tuple[float, float]]:
    return _hand(up={"thumb", "index", "middle", "ring", "pinky"}, thumb_out=True)


def fist() -> list[tuple[float, float]]:
    return _hand(up=set(), thumb_out=False)


def tiny_hand() -> list[tuple[float, float]]:
    return _hand(up={"index", "middle"}, origin=(0.50, 0.70), scale=0.04, thumb_out=False)


class LandmarkHelpers(unittest.TestCase):
    def test_landmark_points_read_xy_objects(self) -> None:
        class LM:
            def __init__(self, x: float, y: float) -> None:
                self.x = x
                self.y = y

        self.assertEqual(landmark_points([LM(0.2, 0.4)]), [(0.2, 0.4)])

    def test_mirror_flips_x_only(self) -> None:
        self.assertEqual(mirror_points([(0.25, 0.40)]), [(0.75, 0.40)])


class PalmCenterTests(unittest.TestCase):
    def test_palm_is_the_middle_of_the_hand(self) -> None:
        points = open_palm()
        palm = palm_center(points)
        xs = [points[i][0] for i in (0, 5, 9, 13, 17)]
        ys = [points[i][1] for i in (0, 5, 9, 13, 17)]
        self.assertAlmostEqual(palm[0], sum(xs) / 5, places=6)
        self.assertAlmostEqual(palm[1], sum(ys) / 5, places=6)
        # Between wrist and the finger bases, not at a fingertip.
        self.assertLess(palm[1], points[0][1])
        self.assertGreater(palm[1], points[12][1])

    def test_a_full_size_hand_is_clear(self) -> None:
        self.assertTrue(hand_is_clear(open_palm(), score=0.9))
        self.assertGreater(palm_span(open_palm()), 0.055)

    def test_a_tiny_or_low_score_hand_is_not_clear(self) -> None:
        self.assertFalse(hand_is_clear(tiny_hand(), score=0.9))
        self.assertFalse(hand_is_clear(open_palm(), score=0.2))
        self.assertFalse(hand_is_clear(None, score=0.9))


class GestureClassificationTests(unittest.TestCase):
    def test_two_fingers_up_is_pass(self) -> None:
        points = peace()
        self.assertEqual(fingers_up(points), frozenset({"index", "middle"}))
        self.assertEqual(classify_gesture(points), "pass")
        features = gesture_features(points)
        self.assertEqual(features["left_wink"], GESTURE_ON)
        self.assertEqual(features["mouth_opening"], 0.0)

    def test_open_palm_is_shoot(self) -> None:
        points = open_palm()
        self.assertEqual(classify_gesture(points), "shoot")
        features = gesture_features(points)
        self.assertEqual(features["mouth_opening"], GESTURE_ON)
        self.assertEqual(features["left_wink"], 0.0)

    def test_fist_fires_neither(self) -> None:
        self.assertIsNone(classify_gesture(fist()))
        features = gesture_features(fist())
        self.assertEqual(features["mouth_opening"], 0.0)
        self.assertEqual(features["left_wink"], 0.0)

    def test_one_finger_is_neither(self) -> None:
        self.assertIsNone(classify_gesture(_hand(up={"index"}, thumb_out=False)))

    def test_three_fingers_is_neither(self) -> None:
        self.assertIsNone(
            classify_gesture(_hand(up={"index", "middle", "ring"}, thumb_out=False))
        )

    def test_pass_and_shoot_are_mutually_exclusive(self) -> None:
        self.assertNotEqual(classify_gesture(peace()), classify_gesture(open_palm()))


def _drive(
    router: AutoSwapRouter,
    machine: ControlStateMachine,
    *,
    nose: tuple[float, float] | None = CENTER,
    face_features: dict[str, float] | None = None,
    face_valid: bool = True,
    hand_points: list[tuple[float, float]] | None = None,
    hand_score: float | None = 0.95,
    now: float = 0.0,
) -> dict[str, object]:
    frame = router.decide(
        face_valid=face_valid,
        nose=nose,
        face_features=face_features if face_features is not None else FACE_NEUTRAL,
        hand_points=hand_points,
        hand_score=hand_score,
    )
    return router.apply(machine, frame, now=now)


def enter_hand(
    router: AutoSwapRouter,
    machine: ControlStateMachine,
    points: list[tuple[float, float]],
    *,
    nose: tuple[float, float] = CENTER,
    face_features: dict[str, float] | None = None,
    start: float = 0.0,
) -> dict[str, object]:
    state: dict[str, object] = {}
    for step in range(HAND_ENTER_FRAMES):
        state = _drive(
            router,
            machine,
            nose=nose,
            face_features=face_features,
            hand_points=points,
            now=start + step * 0.03,
        )
    return state


class AutoSwapTests(unittest.TestCase):
    def test_stays_on_face_when_no_hand(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        router = AutoSwapRouter()
        state = _drive(router, machine, nose=(0.50, 0.38))
        self.assertEqual(state["input_source"], "face")
        self.assertEqual(state["keys"], ["W"])
        self.assertIsNone(state["palm_point"])

    def test_swaps_to_hand_once_a_hand_is_clearly_in_frame(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        router = AutoSwapRouter()
        first = _drive(router, machine, hand_points=peace())
        self.assertEqual(first["input_source"], "face")
        state = enter_hand(router, machine, peace())
        self.assertEqual(state["input_source"], "hand")
        self.assertTrue(state["tracking"])
        self.assertIsNotNone(state["palm_point"])

    def test_returns_to_face_after_the_hand_leaves(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        router = AutoSwapRouter()
        enter_hand(router, machine, peace())
        state: dict[str, object] = {}
        for step in range(HAND_EXIT_FRAMES):
            state = _drive(router, machine, hand_points=None, now=1.0 + step * 0.03)
        self.assertEqual(state["input_source"], "face")

    def test_a_one_frame_hand_dropout_does_not_swap_back(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        router = AutoSwapRouter()
        enter_hand(router, machine, peace())
        flicker = _drive(router, machine, hand_points=None, now=1.0)
        self.assertEqual(flicker["input_source"], "hand")
        back = _drive(router, machine, hand_points=peace(), now=1.03)
        self.assertEqual(back["input_source"], "hand")

    def test_first_palm_becomes_the_look_axis_center(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        router = AutoSwapRouter()
        state = enter_hand(router, machine, open_palm())
        self.assertTrue(state["centered"])
        self.assertEqual(state["keys"], [])
        palm = palm_center(open_palm())
        self.assertAlmostEqual(machine.center[0], palm[0], places=4)
        self.assertAlmostEqual(machine.center[1], palm[1], places=4)

    def test_hand_mode_uses_the_same_wasd_deadzone(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        router = AutoSwapRouter()
        enter_hand(router, machine, fist())
        shifted = [(x, y - 0.12) for x, y in fist()]
        state = _drive(router, machine, hand_points=shifted, now=1.0)
        self.assertEqual(state["input_source"], "hand")
        self.assertEqual(state["direction"], "N")
        self.assertEqual(state["keys"], ["W"])
        self.assertAlmostEqual(palm_center(fist())[1] - 0.12, palm_center(shifted)[1], places=6)

    def test_hand_follow_mode_uses_the_same_outer_ring(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        machine.set_deadzone_mode("follow")
        router = AutoSwapRouter()
        enter_hand(router, machine, fist())
        far = [(x + 0.28, y) for x, y in fist()]
        moving = _drive(router, machine, hand_points=far, now=1.0)
        self.assertEqual(moving["keys"], ["D"])
        self.assertAlmostEqual(moving["nose"]["x"], machine.thresholds.follow_radius, places=3)


class DualInputTests(unittest.TestCase):
    def test_hand_mode_ignores_face_wink_and_mouth(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        router = AutoSwapRouter()
        state = enter_hand(
            router,
            machine,
            fist(),
            face_features={"mouth_opening": 0.20, "left_wink": 0.10},
        )
        self.assertEqual(state["input_source"], "hand")
        self.assertFalse(state["mouth"]["active"])
        self.assertFalse(state["wink"]["active"])
        self.assertNotIn("Space", hold_labels(state))
        self.assertNotIn("L", hold_labels(state))

    def test_face_mode_ignores_hand_gestures(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        router = AutoSwapRouter()
        # Tiny hand is visible to the caller but not "clearly in frame".
        state = _drive(
            router,
            machine,
            face_features=FACE_NEUTRAL,
            hand_points=tiny_hand(),
            hand_score=0.95,
        )
        self.assertEqual(state["input_source"], "face")
        self.assertFalse(state["mouth"]["active"])
        self.assertFalse(state["wink"]["active"])
        # A clear peace sign that has not yet crossed enter_frames is still face.
        one = _drive(router, machine, face_features=FACE_NEUTRAL, hand_points=peace())
        self.assertEqual(one["input_source"], "face")
        self.assertFalse(one["wink"]["active"])

    def test_two_finger_pass_does_not_also_shoot(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        router = AutoSwapRouter()
        state = enter_hand(
            router,
            machine,
            peace(),
            face_features={"mouth_opening": 0.20, "left_wink": 0.0},
        )
        self.assertTrue(state["wink"]["active"])
        self.assertFalse(state["mouth"]["active"])
        self.assertEqual(hold_labels(state), ["L"])

    def test_open_palm_shoot_does_not_also_pass(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        router = AutoSwapRouter()
        state = enter_hand(
            router,
            machine,
            open_palm(),
            face_features={"mouth_opening": 0.0, "left_wink": 0.10},
        )
        self.assertTrue(state["mouth"]["active"])
        self.assertFalse(state["wink"]["active"])
        self.assertEqual(hold_labels(state), ["Space"])


class NoStuckKeysTests(unittest.TestCase):
    def test_open_palm_uses_the_same_shoot_delay(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        router = AutoSwapRouter()
        keyboard = RecordingKeyboard()
        session = InputSession(keyboard, armed=True)
        state = enter_hand(router, machine, open_palm())
        session.apply(state, now=0.0)
        self.assertNotIn("Space", keyboard.held)
        session.apply(state, now=SHOOT_PRESS_DELAY_SECONDS)
        self.assertIn("Space", keyboard.held)

    def test_two_fingers_uses_the_same_pass_delay(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        router = AutoSwapRouter()
        keyboard = RecordingKeyboard()
        session = InputSession(keyboard, armed=True)
        state = enter_hand(router, machine, peace())
        session.apply(state, now=0.0)
        self.assertNotIn("L", keyboard.held)
        session.apply(state, now=PASS_PRESS_DELAY_SECONDS)
        self.assertIn("L", keyboard.held)

    def test_swap_to_hand_releases_face_wasd_and_mouth(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        router = AutoSwapRouter()
        keyboard = RecordingKeyboard()
        session = InputSession(keyboard, armed=True)

        looking = _drive(
            router,
            machine,
            nose=(0.50, 0.35),
            face_features=FACE_SHOOT,
            now=0.0,
        )
        session.apply(looking, now=0.0)
        session.apply(looking, now=SHOOT_PRESS_DELAY_SECONDS)
        self.assertIn("W", keyboard.held)
        self.assertIn("Space", keyboard.held)

        state = enter_hand(
            router, machine, fist(), nose=(0.50, 0.35), face_features=FACE_SHOOT, start=1.0
        )
        session.apply(state, now=1.1)
        self.assertEqual(state["input_source"], "hand")
        self.assertTrue(state["centered"])
        self.assertFalse(state["mouth"]["active"])
        self.assertEqual(keyboard.held, set())

    def test_swap_back_to_face_releases_hand_pass(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        router = AutoSwapRouter()
        keyboard = RecordingKeyboard()
        session = InputSession(keyboard, armed=True)

        state = enter_hand(router, machine, peace(), start=0.0)
        session.apply(state, now=0.1)
        session.apply(state, now=0.1 + PASS_PRESS_DELAY_SECONDS)
        self.assertIn("L", keyboard.held)

        lost: dict[str, object] = {}
        for step in range(HAND_EXIT_FRAMES):
            lost = _drive(
                router,
                machine,
                nose=CENTER,
                face_features=FACE_NEUTRAL,
                hand_points=None,
                now=2.0 + step * 0.03,
            )
            session.apply(lost, now=2.0 + step * 0.03)
        self.assertEqual(lost["input_source"], "face")
        self.assertFalse(lost["wink"]["active"])
        self.assertNotIn("L", keyboard.held)


class HandResetTests(unittest.TestCase):
    def test_reset_recaptures_the_current_palm(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        router = AutoSwapRouter()
        enter_hand(router, machine, fist())
        shifted = [(x + 0.12, y) for x, y in fist()]
        moving = _drive(router, machine, hand_points=shifted, now=1.0)
        self.assertEqual(moving["keys"], ["D"])

        router.reset_centers()
        machine.calibrate(palm_center(shifted))
        after = _drive(router, machine, hand_points=shifted, now=1.2)
        self.assertTrue(after["centered"])
        self.assertEqual(after["keys"], [])
        self.assertEqual(after["input_source"], "hand")

    def test_clear_gestures_does_not_move_the_centre(self) -> None:
        machine = ControlStateMachine()
        machine.calibrate(CENTER)
        machine.update(nose=CENTER, features=FACE_SHOOT, tracking_valid=True, now=0.0)
        self.assertTrue(machine.update(
            nose=CENTER, features=FACE_SHOOT, tracking_valid=True, now=0.1
        )["mouth"]["active"])
        machine.clear_gestures(0.2)
        self.assertEqual(machine.center, CENTER)
        released = machine.update(
            nose=CENTER, features=FACE_NEUTRAL, tracking_valid=True, now=0.3
        )
        self.assertFalse(released["mouth"]["active"])


class WebcamSourceInterpretTests(unittest.TestCase):
    def test_site_reset_in_hand_mode_recentres_the_palm(self) -> None:
        from bridge.source import WebcamSource

        source = WebcamSource()
        source.machine.calibrate(CENTER)
        points = fist()
        state: dict[str, object] = {}
        for step in range(HAND_ENTER_FRAMES):
            state = source.interpret_frame(
                nose=CENTER,
                values=FACE_NEUTRAL,
                face_valid=True,
                hand_landmarks=points,
                hand_score=0.95,
                now=step * 0.03,
            )
        self.assertEqual(state["input_source"], "hand")
        shifted = [(x + 0.12, y) for x, y in points]
        moved = source.interpret_frame(
            nose=CENTER,
            values=FACE_NEUTRAL,
            face_valid=True,
            hand_landmarks=shifted,
            hand_score=0.95,
            now=1.0,
        )
        self.assertEqual(moved["keys"], ["A"])

        source.calibrate()
        after = source.interpret_frame(
            nose=CENTER,
            values={"mouth_opening": 0.20, "left_wink": 0.10},
            face_valid=True,
            hand_landmarks=shifted,
            hand_score=0.95,
            now=1.2,
        )
        self.assertEqual(after["input_source"], "hand")
        self.assertTrue(after["centered"])
        self.assertEqual(after["keys"], [])
        self.assertFalse(after["mouth"]["active"], "face mouth must not fire in hand mode")
        expected = palm_center(mirror_points(shifted))
        self.assertIsNotNone(source.machine.center)
        center = source.machine.center
        assert center is not None
        self.assertAlmostEqual(center[0], expected[0], places=4)
        self.assertAlmostEqual(center[1], expected[1], places=4)


class OverlaySourceLabelTests(unittest.TestCase):
    def test_overlay_names_face_and_hand_without_website_chrome(self) -> None:
        from pathlib import Path

        overlay = (
            Path(__file__).resolve().parent.parent / "bridge" / "overlay_view.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"FACE"', overlay)
        self.assertIn('"HAND"', overlay)
        self.assertIn('"PALM"', overlay)
        self.assertIn('"NO FACE"', overlay)
        self.assertNotIn('"Find your center"', overlay)


if __name__ == "__main__":
    unittest.main()
