"""Glue the vision, controls and output layers into one control loop step.

``ControlPipeline`` is intentionally free of any camera/MediaPipe dependency: it
consumes an already-extracted head pose and mouth-open score. This is what makes
the whole gesture-to-key behaviour unit-testable headlessly (see tests/).
"""

from __future__ import annotations

from dataclasses import dataclass

from .controls.head_direction import DirectionConfig, HeadDirectionClassifier
from .controls.mouth_action import MouthActionDetector
from .controls.wink_action import WinkHoldDetector
from .output.keyboard import KeyboardController
from .vision.head_pose import HeadPose, PoseSmoother


@dataclass
class PipelineState:
    """Snapshot of a single processed frame, useful for the debug overlay."""

    pose: HeadPose
    direction_keys: frozenset[str]
    action_fired: bool
    label: str
    wink_held: bool = False


class ControlPipeline:
    ACTION_KEY = "SPACE"
    PASS_KEY = "L"

    def __init__(
        self,
        keyboard: KeyboardController,
        direction_config: DirectionConfig | None = None,
        smoother: PoseSmoother | None = None,
        mouth: MouthActionDetector | None = None,
        wink: WinkHoldDetector | None = None,
    ):
        self.keyboard = keyboard
        self.classifier = HeadDirectionClassifier(direction_config)
        self.smoother = smoother or PoseSmoother()
        self.mouth = mouth or MouthActionDetector()
        self.wink = wink or WinkHoldDetector()

    def process(
        self,
        pose: HeadPose,
        mouth_open_score: float,
        left_ear: float | None = None,
        right_ear: float | None = None,
    ) -> PipelineState:
        smoothed = self.smoother.update(pose)
        keys = self.classifier.classify(smoothed.yaw, smoothed.pitch)
        wink_held = False
        if left_ear is not None and right_ear is not None:
            wink_held = self.wink.update(left_ear, right_ear)
        held = set(keys)
        if wink_held:
            held.add(self.PASS_KEY)
        self.keyboard.apply_directional(held)

        action = self.mouth.update(mouth_open_score)
        if action:
            self.keyboard.tap(self.ACTION_KEY)

        return PipelineState(
            pose=smoothed,
            direction_keys=keys,
            action_fired=action,
            label=self._label(keys),
            wink_held=wink_held,
        )

    @staticmethod
    def _label(keys: frozenset[str]) -> str:
        if not keys:
            return "NEUTRAL"
        order = {"W": 0, "S": 1, "A": 2, "D": 3}
        names = {"W": "UP", "S": "DOWN", "A": "LEFT", "D": "RIGHT"}
        return "+".join(names[k] for k in sorted(keys, key=order.get))
