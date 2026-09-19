"""Hold L while exactly one eye is closed (pass). Blinks must not hold L."""

from __future__ import annotations


class WinkHoldDetector:
    def __init__(self, closed_threshold: float = 0.16, open_threshold: float = 0.22):
        if closed_threshold >= open_threshold:
            raise ValueError("closed_threshold must be < open_threshold")
        self.closed_threshold = closed_threshold
        self.open_threshold = open_threshold
        self._wink = False

    def reset(self) -> None:
        self._wink = False

    def update(self, left_ear: float, right_ear: float) -> bool:
        left_closed = left_ear < self.closed_threshold
        right_closed = right_ear < self.closed_threshold
        left_open = left_ear > self.open_threshold
        right_open = right_ear > self.open_threshold
        one_wink = (left_closed and right_open) or (right_closed and left_open)
        both_open = left_open and right_open
        both_closed = left_closed and right_closed

        if not self._wink:
            self._wink = one_wink
        elif both_open or both_closed:
            self._wink = False
        return self._wink
