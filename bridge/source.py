"""Control state producers for the bridge server.

Two sources implement the same interface so the orientation UI can be developed
and demoed without a webcam:

- `WebcamSource` drives the real MediaPipe pipeline.
- `MockSource` replays a scripted loop that exercises every UI state.

Keeping both behind one interface means the server, the wire format, and the
frontend never branch on which one is running.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from time import monotonic, sleep
from typing import Any, Iterator

from tracking.controls import ControlStateMachine, ControlThresholds


class ControlSource(ABC):
    """Produces control state dictionaries and optional JPEG frames."""

    def __init__(self, thresholds: ControlThresholds | None = None) -> None:
        self.thresholds = thresholds or ControlThresholds()
        self.machine = ControlStateMachine(thresholds=self.thresholds)

    @abstractmethod
    def frames(self) -> Iterator[tuple[dict[str, object], bytes | None]]:
        """Yield (control_state, jpeg_bytes_or_None) until stopped."""

    def calibrate(self) -> None:
        """Request that the next tracked nose position becomes neutral."""

        self.machine.calibrate(None)

    def stop(self) -> None:
        """Release any hardware. Safe to call more than once."""


class MockSource(ControlSource):
    """Scripted control state for visual development without a camera.

    The loop walks the nose around the directional zones, then fires the mouth
    and wink triggers, then drops tracking, so every screen can be exercised.
    """

    CYCLE_SECONDS = 24.0
    FRAME_SECONDS = 1.0 / 60.0

    def __init__(self, thresholds: ControlThresholds | None = None) -> None:
        super().__init__(thresholds)
        self._started = monotonic()
        self._override: dict[str, Any] | None = None

    def set_override(self, payload: dict[str, Any] | None) -> None:
        """Let the frontend dev panel drive the mock source directly."""

        self._override = payload

    def frames(self) -> Iterator[tuple[dict[str, object], bytes | None]]:
        self.machine.calibrate((0.5, 0.5))
        while True:
            # Pace the loop so mock mode does not spin a core at full speed.
            sleep(self.FRAME_SECONDS)
            yield (self._next_state(), None)

    def _next_state(self) -> dict[str, object]:
        if self._override is not None:
            return self._from_override(self._override)

        elapsed = (monotonic() - self._started) % self.CYCLE_SECONDS
        if elapsed > self.CYCLE_SECONDS - 2.0:
            return self.machine.update(nose=None, features={}, tracking_valid=False)

        # Sweep the nose around a circle so all eight zones are visited.
        angle = (elapsed / 12.0) * 2.0 * math.pi
        radius = 0.11 if elapsed < 12.0 else 0.0
        nose = (0.5 + radius * math.cos(angle), 0.5 - radius * math.sin(angle))

        # After the sweep, pulse the expressions.
        mouth = 0.2 if 13.0 < elapsed < 14.0 or 16.0 < elapsed < 17.0 else 0.0
        wink = 0.1 if 19.0 < elapsed < 20.0 else 0.0
        return self.machine.update(
            nose=nose,
            features={"mouth_opening": mouth, "left_wink": wink},
            tracking_valid=True,
        )

    def _from_override(self, payload: dict[str, Any]) -> dict[str, object]:
        if not payload.get("tracking", True):
            return self.machine.update(nose=None, features={}, tracking_valid=False)
        nose = payload.get("nose") or {}
        return self.machine.update(
            nose=(0.5 + float(nose.get("x", 0.0)), 0.5 + float(nose.get("y", 0.0))),
            features={
                "mouth_opening": float(payload.get("mouth", 0.0)),
                "left_wink": float(payload.get("wink", 0.0)),
            },
            tracking_valid=True,
        )


class WebcamSource(ControlSource):
    """Real tracking source backed by the MediaPipe webcam tracker."""

    NOSE_LANDMARK = 1

    def __init__(
        self,
        thresholds: ControlThresholds | None = None,
        *,
        camera_index: int = 0,
        max_width: int = 640,
        jpeg_quality: int = 70,
    ) -> None:
        super().__init__(thresholds)
        self.camera_index = camera_index
        self.max_width = max_width
        self.jpeg_quality = jpeg_quality
        self._tracker: Any | None = None
        self._recalibrate = False

    def calibrate(self) -> None:
        # Defer to the capture loop so the center comes from a tracked frame.
        self._recalibrate = True

    def frames(self) -> Iterator[tuple[dict[str, object], bytes | None]]:
        import cv2  # type: ignore[import-not-found]

        from tracking.mediapipe_tracker import WebcamFaceTracker

        self._tracker = WebcamFaceTracker(camera_index=self.camera_index, max_width=self.max_width)
        self._tracker.start()
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]

        for tracked in self._tracker.tracked_frames():
            nose = self._nose(tracked.landmarks)
            if self._recalibrate and nose is not None:
                self.machine.calibrate(nose)
                self._recalibrate = False

            values = {
                name: feature.value
                for name, feature in tracked.movement.features.items()
                if feature.available and feature.value is not None
            }
            state = self.machine.update(
                nose=nose,
                features=values,
                tracking_valid=tracked.movement.tracking_valid,
            )

            jpeg: bytes | None = None
            if tracked.image is not None:
                # Mirror the image so the user sees themselves as in a mirror.
                mirrored = cv2.flip(tracked.image, 1)
                ok, buffer = cv2.imencode(".jpg", mirrored, encode_params)
                if ok:
                    jpeg = buffer.tobytes()
            yield (state, jpeg)

    def _nose(self, landmarks: list[Any] | None) -> tuple[float, float] | None:
        if landmarks is None:
            return None
        point = landmarks[self.NOSE_LANDMARK]
        # Mirror x to match the flipped preview the user sees.
        return (1.0 - float(point.x), float(point.y))

    def stop(self) -> None:
        if self._tracker is not None:
            self._tracker.stop()
            self._tracker = None
