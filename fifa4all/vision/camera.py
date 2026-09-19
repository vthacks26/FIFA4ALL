"""Webcam capture. Frames are mirrored by default so looking left = go left."""

from __future__ import annotations

from typing import Any


class Webcam:
    def __init__(self, index: int = 0, mirror: bool = True) -> None:
        import cv2

        self._cv2 = cv2
        self.mirror = mirror
        self.cap = cv2.VideoCapture(index)
        if not self.cap.isOpened():
            raise RuntimeError(
                f"Could not open camera index {index}. Close other apps using "
                "the webcam, then retry."
            )
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    def read(self) -> Any:
        ok, frame = self.cap.read()
        if not ok or frame is None:
            return None
        if self.mirror:
            frame = self._cv2.flip(frame, 1)
        return frame

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def __enter__(self) -> Webcam:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
