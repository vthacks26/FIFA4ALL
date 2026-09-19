"""Map a (smoothed) head pose to WASD movement keys.

Implements the dead zone (joe_plan.txt section 11) and diagonal support
(section 12). The classifier reports *intent* only -- it never touches the
keyboard -- so it is trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DirectionConfig:
    """Threshold configuration in degrees.

    A pose is neutral on an axis while its angle stays within +/- the threshold
    (the dead zone). Values should be tuned experimentally per user.
    """

    yaw_threshold: float = 8.0
    pitch_threshold: float = 8.0


class HeadDirectionClassifier:
    def __init__(self, config: DirectionConfig | None = None):
        self.config = config or DirectionConfig()

    def classify(self, yaw: float, pitch: float) -> frozenset[str]:
        """Return the set of active movement keys, e.g. {"W", "D"} for up-right.

        Empty set means neutral (inside the dead zone on both axes).
        """

        keys: set[str] = set()
        if yaw > self.config.yaw_threshold:
            keys.add("D")
        elif yaw < -self.config.yaw_threshold:
            keys.add("A")

        if pitch > self.config.pitch_threshold:
            keys.add("S")
        elif pitch < -self.config.pitch_threshold:
            keys.add("W")

        return frozenset(keys)
