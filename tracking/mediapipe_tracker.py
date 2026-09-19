"""Optional MediaPipe/OpenCV webcam tracker.

Dependencies are intentionally optional so tests and synthetic fixtures work
without a camera. Install the tracking extras documented in tracking/README.md
before using this module on a Mac.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from time import monotonic
from typing import Any

from tracking.features import FaceFeatureExtractor, FeatureConfig, Point
from tracking.frames import FEATURE_UNITS, MovementFeature, MovementFrame


@dataclass(frozen=True)
class WebcamTrackingFrame:
    """Camera image, movement features, and optional drawing landmarks."""

    image: Any | None
    movement: MovementFrame
    landmarks: list[Any] | None = None


class WebcamFaceTracker:
    """Capture fresh webcam frames and emit movement measurements."""

    def __init__(
        self,
        camera_index: int = 0,
        *,
        max_width: int = 960,
        model_path: str | None = None,
        config: FeatureConfig | None = None,
    ) -> None:
        self.camera_index = camera_index
        self.max_width = max_width
        self.model_path = model_path or os.environ.get("FIFA4ALL_FACE_LANDMARKER_MODEL")
        self.extractor = FaceFeatureExtractor(config)
        self._cv2: Any | None = None
        self._face_mesh: Any | None = None
        self._landmarker: Any | None = None
        self._capture: Any | None = None
        self._mp: Any | None = None

    def __enter__(self) -> "WebcamFaceTracker":
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    def start(self) -> None:
        os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.getcwd(), ".cache", "matplotlib"))
        import cv2  # type: ignore[import-not-found]
        import mediapipe as mp  # type: ignore[import-not-found]

        self._mp = mp
        self._cv2 = cv2
        self._face_mesh = self._create_face_mesh(mp) if hasattr(mp, "solutions") else None
        if self._face_mesh is None:
            self._landmarker = self._create_landmarker(mp)
        self._capture = cv2.VideoCapture(self.camera_index)
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self._capture.isOpened():
            raise RuntimeError(f"Could not open camera index {self.camera_index}")

    def stop(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        if self._face_mesh is not None:
            self._face_mesh.close()
            self._face_mesh = None
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
        if self._cv2 is not None:
            self._cv2.destroyAllWindows()

    def frames(self) -> Iterator[tuple[Any, MovementFrame]]:
        for tracked in self.tracked_frames():
            yield tracked.image, tracked.movement

    def tracked_frames(self) -> Iterator[WebcamTrackingFrame]:
        if self._capture is None or (self._face_mesh is None and self._landmarker is None) or self._cv2 is None:
            self.start()

        assert self._capture is not None
        assert self._cv2 is not None

        while True:
            frame = self._read_fresh_frame()
            if frame is None:
                yield WebcamTrackingFrame(None, _invalid_frame("camera_read_failed"))
                continue

            frame = self._resize(frame)
            result = self._detect(frame)
            landmarks = _result_landmarks(result)
            if landmarks is None:
                self.extractor.reset()
                yield WebcamTrackingFrame(frame, _invalid_frame("face_not_found"))
                continue

            points = _mediapipe_points(landmarks)
            movement = self.extractor.from_named_points(points, timestamp_monotonic=monotonic())
            yield WebcamTrackingFrame(frame, movement, landmarks)

    def _read_fresh_frame(self) -> Any | None:
        assert self._capture is not None
        frame = None
        ok = False
        for _ in range(3):
            ok, frame = self._capture.read()
            if not ok:
                return None
        return frame

    def _resize(self, frame: Any) -> Any:
        assert self._cv2 is not None
        height, width = frame.shape[:2]
        if width <= self.max_width:
            return frame
        scale = self.max_width / width
        return self._cv2.resize(frame, (self.max_width, int(height * scale)))

    def _create_face_mesh(self, mp: Any) -> Any:
        return mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def _create_landmarker(self, mp: Any) -> Any:
        if not self.model_path:
            raise RuntimeError(
                "MediaPipe Tasks requires a face landmarker model. Set "
                "FIFA4ALL_FACE_LANDMARKER_MODEL to a local .task file."
            )
        base_options = mp.tasks.BaseOptions(model_asset_path=self.model_path)
        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_faces=1,
        )
        return mp.tasks.vision.FaceLandmarker.create_from_options(options)

    def _detect(self, frame: Any) -> Any:
        assert self._cv2 is not None
        assert self._mp is not None

        rgb = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
        if self._face_mesh is not None:
            return self._face_mesh.process(rgb)

        assert self._landmarker is not None
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        return self._landmarker.detect(image)


def _invalid_frame(reason: str) -> MovementFrame:
    return MovementFrame(
        timestamp_monotonic=monotonic(),
        tracking_valid=False,
        features={name: MovementFeature.unavailable(unit, reason) for name, unit in FEATURE_UNITS.items()},
    )


def _mediapipe_points(landmarks: list[Any]) -> dict[str, Point]:
    return {
        "left_cheek": _xy(landmarks[234]),
        "right_cheek": _xy(landmarks[454]),
        "upper_lip": _xy(landmarks[13]),
        "lower_lip": _xy(landmarks[14]),
        "nose_tip": _xy(landmarks[1]),
        "left_eye": _xy(landmarks[33]),
        "right_eye": _xy(landmarks[263]),
        "left_upper_eyelid": _xy(landmarks[159]),
        "left_lower_eyelid": _xy(landmarks[145]),
        "right_upper_eyelid": _xy(landmarks[386]),
        "right_lower_eyelid": _xy(landmarks[374]),
    }


def _result_landmarks(result: Any) -> list[Any] | None:
    if getattr(result, "multi_face_landmarks", None):
        return result.multi_face_landmarks[0].landmark
    if getattr(result, "face_landmarks", None):
        return result.face_landmarks[0]
    return None


def _xy(landmark: Any) -> Point:
    return (float(landmark.x), float(landmark.y))
