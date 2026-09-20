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

from tracking.controls import ControlStateMachine, ControlThresholds, DeadzoneMode, parse_deadzone_mode
from tracking.hands import AutoSwapRouter, landmark_points, mirror_points


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

    def set_deadzone_mode(self, mode: object) -> DeadzoneMode:
        """Switch fixed vs follow on the live machine this process injects."""

        return self.machine.set_deadzone_mode(parse_deadzone_mode(mode))

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
        camera_name: str | None = None,
        camera_unique_id: str | None = None,
        max_width: int = 640,
        jpeg_quality: int = 70,
    ) -> None:
        super().__init__(thresholds)
        self.camera_index = camera_index
        self.camera_name = camera_name
        self.camera_unique_id = camera_unique_id
        self.max_width = max_width
        self.jpeg_quality = jpeg_quality
        self._tracker: Any | None = None
        self._recalibrate = False
        self.router = AutoSwapRouter()
        # Latest mirrored BGR frame, for the on-screen overlay. The MJPEG bytes
        # are no use there because the overlay draws before encoding.
        self.last_frame: Any | None = None

    def calibrate(self) -> None:
        # Defer to the capture loop so the center comes from a tracked frame.
        # Overlay RESET and POST /calibrate both land here — same machine that
        # InputSession reads for Quartz WASD / Space / L.
        self._recalibrate = True
        # Drop both look-axis homes so the next nose and the next palm each
        # recapture centre the way the first valid point does at start.
        self.router.reset_centers()

    def apply_pending_calibrate(
        self,
        nose: tuple[float, float] | None,
        values: dict[str, float],
    ) -> bool:
        """Apply a deferred RESET onto the live ControlStateMachine.

        Returns True when this frame became the new neutral. Safe to call with
        no camera: the capture loop uses this so site calibrate and Luna inject
        cannot drift onto separate trackers.
        """

        if not self._recalibrate or nose is None:
            return False
        left = values.get("left_eye_opening")
        right = values.get("right_eye_opening")
        eye_rest = max(left, right) if left is not None and right is not None else None
        self.machine.calibrate(
            nose,
            mouth_rest=values.get("mouth_opening"),
            eye_rest=eye_rest,
            brow_rest=values.get("eyebrow_raise"),
        )
        self._recalibrate = False
        return True

    def interpret_frame(
        self,
        *,
        nose: tuple[float, float] | None,
        values: dict[str, float],
        face_valid: bool,
        hand_landmarks: list[Any] | None = None,
        hand_score: float | None = None,
        now: float | None = None,
    ) -> dict[str, object]:
        """Auto-swap one face+hand observation onto the live control machine.

        Camera-free so tests can cover hand mode without opening the MacBook
        camera. ``frames`` is the live wrapper around this.
        """

        hand_points = None
        if hand_landmarks:
            hand_points = mirror_points(landmark_points(hand_landmarks))
        decided = self.router.decide(
            face_valid=face_valid,
            nose=nose,
            face_features=values,
            hand_points=hand_points,
            hand_score=hand_score,
        )
        calibrate_values = values if decided.source == "face" else {}
        self.apply_pending_calibrate(decided.look, calibrate_values)
        return self.router.apply(self.machine, decided, now=now)

    def frames(self) -> Iterator[tuple[dict[str, object], bytes | None]]:
        import cv2  # type: ignore[import-not-found]

        from tracking.mediapipe_tracker import WebcamFaceTracker

        self._tracker = WebcamFaceTracker(
            camera_index=self.camera_index,
            camera_name=self.camera_name,
            camera_unique_id=self.camera_unique_id,
            max_width=self.max_width,
        )
        self._tracker.start()
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]

        for tracked in self._tracker.tracked_frames():
            nose = self._nose(tracked.landmarks)
            values = {
                name: feature.value
                for name, feature in tracked.movement.features.items()
                if feature.available and feature.value is not None
            }
            state = self.interpret_frame(
                nose=nose,
                values=values,
                face_valid=tracked.movement.tracking_valid,
                hand_landmarks=tracked.hand_landmarks,
                hand_score=tracked.hand_score,
            )
            eyebrow = state.get("eyebrow")
            if isinstance(eyebrow, dict) and eyebrow.get("fired"):
                print(
                    "Reset: eyebrow-raise pose baseline cleared. "
                    "Next valid face is neutral.",
                    flush=True,
                )

            jpeg: bytes | None = None
            if tracked.image is not None:
                # Mirror the image so the user sees themselves as in a mirror.
                mirrored = cv2.flip(tracked.image, 1)
                self.last_frame = mirrored
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
