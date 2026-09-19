"""Glue the vision, controls and output layers into one control loop step.

``ControlPipeline`` is intentionally free of any camera/MediaPipe dependency: it
consumes an already-extracted head pose and mouth-open score. This is what makes
the whole gesture-to-key behaviour unit-testable headlessly (see tests/).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .controls.head_direction import DirectionConfig, HeadDirectionClassifier
from .controls.mouth_action import MouthActionDetector
from .output.keyboard import KeyboardController
from .vision.head_pose import HeadPose, PoseSmoother


@dataclass
class PipelineState:
    """Snapshot of a single processed frame, useful for the debug overlay."""

    pose: HeadPose
    direction_keys: frozenset[str]
    action_fired: bool
    label: str


class ControlPipeline:
    ACTION_KEY = "SPACE"

    def __init__(
        self,
        keyboard: KeyboardController,
        direction_config: DirectionConfig | None = None,
        smoother: PoseSmoother | None = None,
        mouth: MouthActionDetector | None = None,
    ):
        self.keyboard = keyboard
        self.classifier = HeadDirectionClassifier(direction_config)
        self.smoother = smoother or PoseSmoother()
        self.mouth = mouth or MouthActionDetector()

    def process(self, pose: HeadPose, mouth_open_score: float) -> PipelineState:
        smoothed = self.smoother.update(pose)
        keys = self.classifier.classify(smoothed.yaw, smoothed.pitch)
        self.keyboard.apply_directional(keys)

        action = self.mouth.update(mouth_open_score)
        if action:
            self.keyboard.tap(self.ACTION_KEY)

        return PipelineState(
            pose=smoothed,
            direction_keys=keys,
            action_fired=action,
            label=self._label(keys),
        )

    @staticmethod
    def _label(keys: frozenset[str]) -> str:
        if not keys:
            return "NEUTRAL"
        order = {"W": 0, "S": 1, "A": 2, "D": 3}
        names = {"W": "UP", "S": "DOWN", "A": "LEFT", "D": "RIGHT"}
        return "+".join(names[k] for k in sorted(keys, key=order.get))
