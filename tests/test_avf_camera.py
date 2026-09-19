"""Tests for the AVFoundation camera capture path.

No camera and no PyObjC required: the pixel-buffer conversion is exercised
against a fake CoreVideo surface, and the publish/read handoff is driven
directly, which is the part that used to race.
"""

from __future__ import annotations

import threading
import unittest

import numpy as np

from tracking.avf_camera import (
    _LIVE_CAMERAS,
    AVFCamera,
    CameraError,
    CameraNotStarted,
    _frame_from_pixel_buffer,
    _stop_live_cameras,
)


class FakeQuartz:
    """Stands in for the Quartz CoreVideo functions on a fixed buffer."""

    kCVPixelBufferLock_ReadOnly = 1

    def __init__(self, width: int, height: int, stride: int, data: bytes) -> None:
        self._width, self._height, self._stride, self._data = width, height, stride, data

    def CVPixelBufferGetWidth(self, _buf: object) -> int:
        return self._width

    def CVPixelBufferGetHeight(self, _buf: object) -> int:
        return self._height

    def CVPixelBufferGetBytesPerRow(self, _buf: object) -> int:
        return self._stride

    def CVPixelBufferGetBaseAddress(self, _buf: object) -> bytes | None:
        return self._data


def bgra_surface(width: int, height: int, padding: int = 0) -> tuple[FakeQuartz, np.ndarray]:
    """Build a BGRA surface with `padding` junk bytes on the end of each row."""

    stride = width * 4 + padding
    expected = np.zeros((height, width, 3), dtype=np.uint8)
    rows = bytearray()
    for y in range(height):
        for x in range(width):
            blue, green, red = (x * 3) % 256, (y * 5) % 256, (x + y) % 256
            rows += bytes((blue, green, red, 255))
            expected[y, x] = (blue, green, red)
        rows += b"\xAB" * padding
    return FakeQuartz(width, height, stride, bytes(rows)), expected


class PixelBufferConversionTests(unittest.TestCase):
    def test_converts_bgra_surface_to_bgr_array(self) -> None:
        quartz, expected = bgra_surface(8, 4)
        frame = _frame_from_pixel_buffer(object(), quartz)
        np.testing.assert_array_equal(frame, expected)

    def test_strips_row_padding_when_stride_exceeds_width(self) -> None:
        # A 6px row is 24 bytes of pixels, but CoreVideo may hand back a 32 byte
        # stride. Taking the stride as the width would shear the image.
        quartz, expected = bgra_surface(6, 3, padding=8)
        frame = _frame_from_pixel_buffer(object(), quartz)
        self.assertEqual(frame.shape, (3, 6, 3))
        np.testing.assert_array_equal(frame, expected)

    def test_returns_contiguous_array_detached_from_the_source_buffer(self) -> None:
        quartz, _ = bgra_surface(4, 2)
        frame = _frame_from_pixel_buffer(object(), quartz)
        self.assertTrue(frame.flags["C_CONTIGUOUS"])
        self.assertTrue(frame.flags["OWNDATA"])

    def test_raises_when_the_buffer_has_no_base_address(self) -> None:
        quartz = FakeQuartz(4, 2, 16, b"")
        quartz.CVPixelBufferGetBaseAddress = lambda _buf: None  # type: ignore[assignment]
        with self.assertRaises(CameraError):
            _frame_from_pixel_buffer(object(), quartz)

    def test_raises_when_the_buffer_reports_zero_size(self) -> None:
        quartz, _ = bgra_surface(4, 2)
        quartz.CVPixelBufferGetWidth = lambda _buf: 0  # type: ignore[assignment]
        with self.assertRaises(CameraError):
            _frame_from_pixel_buffer(object(), quartz)


class FakeSession:
    """Stands in for AVCaptureSession."""

    def __init__(self, events: list[str]) -> None:
        self.running = True
        self._events = events

    def isRunning(self) -> bool:
        return self.running

    def stopRunning(self) -> None:
        self.running = False
        self._events.append("stop-session")

    def removeOutput_(self, _output: object) -> None:
        self._events.append("remove-output")

    def removeInput_(self, _input: object) -> None:
        self._events.append("remove-input")


class FakeOutput:
    """Stands in for AVCaptureVideoDataOutput."""

    def __init__(self, events: list[str]) -> None:
        self.delegate: object = object()
        self._events = events

    def setSampleBufferDelegate_queue_(self, delegate: object, _queue: object) -> None:
        self.delegate = delegate
        self._events.append("detach-delegate" if delegate is None else "attach-delegate")


class RunningCamera(AVFCamera):
    """An AVFCamera with the ObjC session stubbed out."""

    def __init__(self) -> None:
        super().__init__(unique_id="fake")
        self.events: list[str] = []
        self.session = FakeSession(self.events)
        self.output = FakeOutput(self.events)
        self._session = self.session
        self._output = self.output
        self._queue = "fake-queue"
        self._delegate = object()
        self._input = object()

    def _drain(self, queue: object) -> None:  # type: ignore[override]
        self.events.append(f"drain:{queue}")


class ReadContractTests(unittest.TestCase):
    def test_read_before_start_is_an_error(self) -> None:
        with self.assertRaises(CameraError):
            AVFCamera(unique_id="fake").read(timeout=0.01)

    def test_read_returns_a_published_frame(self) -> None:
        camera = RunningCamera()
        frame = np.full((2, 2, 3), 7, dtype=np.uint8)
        camera._publish(frame)
        ok, got = camera.read(timeout=0.01)
        self.assertTrue(ok)
        np.testing.assert_array_equal(got, frame)

    def test_read_times_out_when_no_frame_arrives(self) -> None:
        ok, frame = RunningCamera().read(timeout=0.01)
        self.assertFalse(ok)
        self.assertIsNone(frame)

    def test_read_waits_for_a_frame_that_arrives_late(self) -> None:
        camera = RunningCamera()
        frame = np.full((2, 2, 3), 3, dtype=np.uint8)
        threading.Timer(0.02, lambda: camera._publish(frame)).start()
        ok, got = camera.read(timeout=2.0)
        self.assertTrue(ok)
        np.testing.assert_array_equal(got, frame)

    def test_read_does_not_return_the_same_frame_twice(self) -> None:
        camera = RunningCamera()
        camera._publish(np.zeros((2, 2, 3), dtype=np.uint8))
        self.assertTrue(camera.read(timeout=0.01)[0])
        ok, frame = camera.read(timeout=0.01)
        self.assertFalse(ok, "a second read with no new frame should report no frame")
        self.assertIsNone(frame)

    def test_read_returns_only_the_newest_frame(self) -> None:
        camera = RunningCamera()
        camera._publish(np.full((2, 2, 3), 1, dtype=np.uint8))
        camera._publish(np.full((2, 2, 3), 9, dtype=np.uint8))
        ok, frame = camera.read(timeout=0.01)
        self.assertTrue(ok)
        np.testing.assert_array_equal(frame, np.full((2, 2, 3), 9, dtype=np.uint8))

    def test_delegate_error_surfaces_on_the_next_read(self) -> None:
        camera = RunningCamera()
        camera._publish_error("ValueError: bad surface")
        with self.assertRaises(CameraError) as caught:
            camera.read(timeout=0.01)
        self.assertIn("bad surface", str(caught.exception))

    def test_a_failed_frame_is_consumed_not_replayed_as_fresh(self) -> None:
        # The error must also advance the read cursor. Otherwise the next read
        # finds the cursor behind and hands back the previous image as new.
        camera = RunningCamera()
        first = np.full((2, 2, 3), 4, dtype=np.uint8)
        camera._publish(first)
        self.assertTrue(camera.read(timeout=0.01)[0])
        camera._publish_error("ValueError: bad surface")
        with self.assertRaises(CameraError):
            camera.read(timeout=0.01)
        ok, frame = camera.read(timeout=0.01)
        self.assertFalse(ok, "the previous frame must not come back as fresh")
        self.assertIsNone(frame)

    def test_error_is_reported_once_and_then_cleared(self) -> None:
        camera = RunningCamera()
        camera._publish_error("ValueError: bad surface")
        with self.assertRaises(CameraError):
            camera.read(timeout=0.01)
        ok, _ = camera.read(timeout=0.01)
        self.assertFalse(ok, "the error should not be raised a second time")


class StopTests(unittest.TestCase):
    def test_stop_is_idempotent_before_start(self) -> None:
        camera = AVFCamera(unique_id="fake")
        camera.stop()
        camera.stop()
        self.assertFalse(camera.is_open)

    def test_stop_releases_the_frame_and_the_session(self) -> None:
        camera = RunningCamera()
        camera._publish(np.zeros((2, 2, 3), dtype=np.uint8))
        camera.stop()
        self.assertIsNone(camera._frame)
        self.assertFalse(camera.is_open)
        self.assertFalse(camera.session.running)

    def test_stop_detaches_the_delegate_so_no_callback_can_arrive_after(self) -> None:
        # The delegate must be unhooked from the output before it is dropped,
        # or a late frame calls into a freed object.
        camera = RunningCamera()
        camera.stop()
        self.assertIsNone(camera.output.delegate)
        self.assertIsNone(camera._delegate)

    def test_stop_drains_the_camera_queue_after_detaching_the_delegate(self) -> None:
        # A callback AVFoundation already dispatched will still run after the
        # delegate is cleared. Letting one reach a shutting-down interpreter
        # segfaults in PyGILState_Ensure, so stop() must wait for the queue to
        # drain, and only then drop the delegate.
        camera = RunningCamera()
        camera.stop()
        self.assertEqual(
            camera.events,
            [
                "stop-session",
                "remove-output",
                "remove-input",
                "detach-delegate",
                "drain:fake-queue",
            ],
        )
        self.assertIsNone(camera._delegate)
        self.assertIsNone(camera._queue)

    def test_exit_hook_stops_a_camera_the_caller_forgot(self) -> None:
        # A session still live when the interpreter exits is the crash this
        # class exists to prevent, so exit must tear one down even if nobody
        # called stop().
        camera = RunningCamera()
        _LIVE_CAMERAS.add(camera)
        _stop_live_cameras()
        self.assertFalse(camera.is_open)
        self.assertIn("drain:fake-queue", camera.events)

    def test_exit_hook_ignores_an_already_stopped_camera(self) -> None:
        camera = RunningCamera()
        _LIVE_CAMERAS.add(camera)
        camera.stop()
        _stop_live_cameras()  # must not raise
        self.assertFalse(camera.is_open)

    def test_stop_clears_a_pending_error_so_it_cannot_leak_into_a_new_session(self) -> None:
        camera = RunningCamera()
        camera._publish_error("ValueError: bad surface")
        camera.stop()
        self.assertIsNone(camera._error)

    def test_read_after_stop_reports_not_started(self) -> None:
        camera = RunningCamera()
        camera.stop()
        with self.assertRaises(CameraNotStarted):
            camera.read(timeout=0.01)

    def test_stop_is_idempotent_after_running(self) -> None:
        camera = RunningCamera()
        camera.stop()
        camera.stop()
        self.assertFalse(camera.is_open)


if __name__ == "__main__":
    unittest.main()
