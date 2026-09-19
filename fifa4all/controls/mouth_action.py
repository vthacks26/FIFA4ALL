"""Detect the mouth-open ("O") gesture and turn it into a single action.

Implements the activation cycle from joe_plan.txt section 14: the gesture fires
exactly once when the mouth opens, then must return to neutral before it can
fire again. Hysteresis (separate open/close thresholds) avoids flicker while
talking.
"""

from __future__ import annotations


class MouthActionDetector:
    def __init__(self, open_threshold: float = 0.5, close_threshold: float = 0.3):
        if close_threshold >= open_threshold:
            raise ValueError("close_threshold must be < open_threshold")
        self.open_threshold = open_threshold
        self.close_threshold = close_threshold
        self._armed = True

    def reset(self) -> None:
        self._armed = True

    def update(self, mouth_open_score: float) -> bool:
        """Feed the current mouth-open score (e.g. MediaPipe ``jawOpen``).

        Returns ``True`` on the single frame the gesture activates.
        """

        if self._armed and mouth_open_score >= self.open_threshold:
            self._armed = False
            return True
        if not self._armed and mouth_open_score <= self.close_threshold:
            self._armed = True
        return False
