"""Hand landmarks, palm centre, and auto-swap with face controls.

MediaPipe Hands (same ``mediapipe==0.10.14`` stack as Face Mesh) supplies 21
landmarks. This module is pure geometry and routing so tests do not need a
camera or OpenPose.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Literal, Mapping, Sequence

from tracking.controls import ControlStateMachine, _point

Point = tuple[float, float]
InputSource = Literal["face", "hand"]

# MediaPipe Hands (21): wrist, thumb, index, middle, ring, pinky.
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP = 5, 6, 7, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9, 10, 11, 12
RING_MCP, RING_PIP, RING_DIP, RING_TIP = 13, 14, 15, 16
PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP = 17, 18, 19, 20

# Middle of the hand: wrist plus the four finger bases.
PALM_LANDMARKS: tuple[int, ...] = (WRIST, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP)

FINGERS: tuple[str, ...] = ("thumb", "index", "middle", "ring", "pinky")
FINGER_TIP = {
    "thumb": THUMB_TIP,
    "index": INDEX_TIP,
    "middle": MIDDLE_TIP,
    "ring": RING_TIP,
    "pinky": PINKY_TIP,
}
FINGER_PIP = {
    "thumb": THUMB_IP,
    "index": INDEX_PIP,
    "middle": MIDDLE_PIP,
    "ring": RING_PIP,
    "pinky": PINKY_PIP,
}
FINGER_MCP = {
    "thumb": THUMB_MCP,
    "index": INDEX_MCP,
    "middle": MIDDLE_MCP,
    "ring": RING_MCP,
    "pinky": PINKY_MCP,
}

# High enough to cross ControlThresholds.mouth_open / wink_on; zero at rest so
# the existing 0.2s InputSession hold delay still applies to pass and shoot.
GESTURE_ON = 0.20
GESTURE_OFF = 0.0

# A hand at the far edge of the MacBook frame is not "clearly in frame".
MIN_PALM_SPAN = 0.055
MIN_HAND_SCORE = 0.65
FRAME_MARGIN = 0.02

# Consecutive frames before swapping. 2 frames in is snappy; 4 out avoids
# dropping WASD every time Hands flickers for a frame.
HAND_ENTER_FRAMES = 2
HAND_EXIT_FRAMES = 4


def landmark_points(landmarks: Sequence[object]) -> list[Point]:
    """Pull (x, y) from MediaPipe-style landmark objects or already-numeric points."""

    points: list[Point] = []
    for item in landmarks:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            points.append((float(item[0]), float(item[1])))
            continue
        x = getattr(item, "x", None)
        y = getattr(item, "y", None)
        if x is None or y is None:
            raise ValueError("hand landmark is missing x/y")
        points.append((float(x), float(y)))
    return points


def mirror_points(points: Sequence[Point]) -> list[Point]:
    """Mirror x to match the flipped preview the user sees."""

    return [(1.0 - x, y) for x, y in points]


def palm_center(points: Sequence[Point]) -> Point:
    """Middle of the hand: mean of wrist and MCP joints."""

    if len(points) <= max(PALM_LANDMARKS):
        raise ValueError("need all 21 MediaPipe Hands landmarks")
    xs = [points[i][0] for i in PALM_LANDMARKS]
    ys = [points[i][1] for i in PALM_LANDMARKS]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def palm_span(points: Sequence[Point]) -> float:
    """Index-MCP to pinky-MCP distance, in normalized image units."""

    index = points[INDEX_MCP]
    pinky = points[PINKY_MCP]
    return hypot(index[0] - pinky[0], index[1] - pinky[1])


def hand_is_clear(
    points: Sequence[Point] | None,
    *,
    score: float | None = None,
    min_score: float = MIN_HAND_SCORE,
    min_span: float = MIN_PALM_SPAN,
) -> bool:
    """True when a hand is large enough, in-frame, and confidently detected."""

    if points is None or len(points) <= max(PALM_LANDMARKS):
        return False
    if score is not None and score < min_score:
        return False
    if palm_span(points) < min_span:
        return False
    for index in PALM_LANDMARKS:
        x, y = points[index]
        if not (FRAME_MARGIN <= x <= 1.0 - FRAME_MARGIN and FRAME_MARGIN <= y <= 1.0 - FRAME_MARGIN):
            return False
    return True


def finger_up(points: Sequence[Point], finger: str) -> bool:
    """True when that digit is extended toward the top of the camera frame.

    Image y grows downward, so an extended finger has its tip above its PIP
    and farther from the MCP than the PIP is.
    """

    if finger not in FINGER_TIP:
        raise ValueError(f"unknown finger {finger!r}")
    if finger == "thumb":
        return _thumb_extended(points)
    tip = points[FINGER_TIP[finger]]
    pip = points[FINGER_PIP[finger]]
    mcp = points[FINGER_MCP[finger]]
    tip_reach = hypot(tip[0] - mcp[0], tip[1] - mcp[1])
    pip_reach = hypot(pip[0] - mcp[0], pip[1] - mcp[1])
    pointing_up = tip[1] < pip[1] - 0.008
    return pointing_up and tip_reach > pip_reach * 1.08


def _thumb_extended(points: Sequence[Point]) -> bool:
    """Thumb is open when its tip sits away from the index MCP / palm."""

    tip = points[THUMB_TIP]
    ip = points[THUMB_IP]
    index_mcp = points[INDEX_MCP]
    tip_gap = hypot(tip[0] - index_mcp[0], tip[1] - index_mcp[1])
    ip_gap = hypot(ip[0] - index_mcp[0], ip[1] - index_mcp[1])
    return tip_gap > ip_gap * 1.15 and tip_gap > 0.04


def fingers_up(points: Sequence[Point]) -> frozenset[str]:
    return frozenset(name for name in FINGERS if finger_up(points, name))


def classify_gesture(points: Sequence[Point]) -> Literal["pass", "shoot"] | None:
    """Two fingers up (index+middle) is pass; open palm is shoot."""

    raised = fingers_up(points)
    four = {"index", "middle", "ring", "pinky"}
    if four <= raised and "thumb" in raised:
        return "shoot"
    # Peace sign: index + middle, ring and pinky folded. A slightly open
    # thumb still counts as pass; open palm (shoot) needs all five.
    extra = raised - {"index", "middle"}
    if {"index", "middle"} <= raised and extra <= {"thumb"}:
        return "pass"
    return None


def gesture_features(points: Sequence[Point]) -> dict[str, float]:
    """Map hand gestures onto the same mouth / wink channels the face uses.

    InputSession already waits 0.2s on those channels before Space / L.
    """

    gesture = classify_gesture(points)
    return {
        "mouth_opening": GESTURE_ON if gesture == "shoot" else GESTURE_OFF,
        "left_wink": GESTURE_ON if gesture == "pass" else GESTURE_OFF,
    }


@dataclass(frozen=True)
class SourceFrame:
    """One camera frame after auto-swap has chosen face or hand."""

    source: InputSource
    look: Point | None
    features: Mapping[str, float]
    tracking_valid: bool
    swapped: bool = False


@dataclass
class AutoSwapRouter:
    """Pick hand when a hand is clearly in frame; otherwise face.

    No UI toggle. Switching stashes each source's look-axis centre so a palm
    and a nose do not share one deadzone, and clears expression latches so a
    face wink cannot leave L held after a hand takes over.
    """

    enter_frames: int = HAND_ENTER_FRAMES
    exit_frames: int = HAND_EXIT_FRAMES
    source: InputSource = "face"
    _seen: int = 0
    _missed: int = 0
    _last_palm: Point | None = None
    _face_center: Point | None = None
    _face_home: Point | None = None
    _hand_center: Point | None = None
    _hand_home: Point | None = None

    def reset_centers(self) -> None:
        """Forget both look-axis homes. Next valid point of the active source is centre."""

        self._face_center = None
        self._face_home = None
        self._hand_center = None
        self._hand_home = None
        self._last_palm = None

    def decide(
        self,
        *,
        face_valid: bool,
        nose: Point | None,
        face_features: Mapping[str, float],
        hand_points: Sequence[Point] | None,
        hand_score: float | None = None,
    ) -> SourceFrame:
        """Choose the active source for this frame. Does not touch the machine."""

        clear = hand_is_clear(hand_points, score=hand_score)
        hand_feats: dict[str, float] = {}
        if clear and hand_points is not None:
            self._seen += 1
            self._missed = 0
            self._last_palm = palm_center(hand_points)
            hand_feats = gesture_features(hand_points)
        else:
            self._missed += 1
            self._seen = 0

        previous = self.source
        if self.source != "hand" and self._seen >= self.enter_frames:
            self.source = "hand"
        elif self.source == "hand" and self._missed >= self.exit_frames:
            self.source = "face"
        swapped = self.source != previous

        if self.source == "hand":
            look = self._last_palm
            tracking = look is not None
            # Stale shoot/pass from a dropped hand must not keep Space/L down.
            features = hand_feats if clear else {}
            return SourceFrame("hand", look, features, tracking, swapped)

        tracking = bool(face_valid and nose is not None)
        features = dict(face_features) if tracking else {}
        return SourceFrame("face", nose if tracking else None, features, tracking, swapped)

    def apply(
        self,
        machine: ControlStateMachine,
        frame: SourceFrame,
        *,
        now: float | None = None,
    ) -> dict[str, object]:
        """Drive the shared control machine from one auto-swapped frame."""

        if frame.swapped:
            self._stash_and_restore(machine, frame.source)
            machine.clear_gestures(now)
        state = machine.update(
            nose=frame.look,
            features=frame.features,
            tracking_valid=frame.tracking_valid,
            now=now,
        )
        self._capture_active(machine, frame.source)
        state["input_source"] = frame.source
        state["palm_point"] = _point(frame.look) if frame.source == "hand" else None
        return state

    def _stash_and_restore(self, machine: ControlStateMachine, incoming: InputSource) -> None:
        outgoing: InputSource = "face" if incoming == "hand" else "hand"
        self._store(outgoing, machine.center, machine.home)
        center, home = self._load(incoming)
        machine.center = center
        machine.home = home

    def _capture_active(self, machine: ControlStateMachine, source: InputSource) -> None:
        self._store(source, machine.center, machine.home)

    def _store(self, source: InputSource, center: Point | None, home: Point | None) -> None:
        if source == "hand":
            self._hand_center = center
            self._hand_home = home
        else:
            self._face_center = center
            self._face_home = home

    def _load(self, source: InputSource) -> tuple[Point | None, Point | None]:
        if source == "hand":
            return (self._hand_center, self._hand_home)
        return (self._face_center, self._face_home)
