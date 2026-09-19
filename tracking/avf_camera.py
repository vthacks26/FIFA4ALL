"""Mac webcam capture that owns its AVFoundation session.

OpenCV's macOS backend hands a live ``CVPixelBuffer`` across threads: its
delegate swaps the buffer on the camera's dispatch queue while the reader locks
that same buffer on the main thread, with nothing serialising the two. The
result is an over-release (``SIGTRAP`` in ``CFRelease``) or a read of a freed
buffer (``SIGSEGV`` in ``CVPixelBufferLockBaseAddress``). Both signatures showed
up repeatedly in this project's crash logs.

This module removes the hazard rather than narrowing it. The delegate copies the
pixel buffer into a numpy array *on the camera queue, while the buffer is
provably alive*, and only that array is published to the reader. No CoreVideo
buffer lifetime ever crosses a thread boundary, so there is nothing to race
over.

Frames are BGR uint8, matching what the rest of the tracking code expects from
OpenCV.
"""

from __future__ import annotations

import atexit
import threading
from typing import Any

import numpy as np


BGRA_CHANNELS = 4

# Cameras that have been started and not yet stopped. A delegate callback that
# reaches a shutting-down interpreter segfaults in `PyGILState_Ensure`, so every
# session must be torn down while Python is still fully alive — including when a
# caller forgets to stop one, or an error path skips it.
#
# Deliberately a strong set, not a weak one: a forgotten camera is exactly the
# case this exists to catch, and a weak reference would let it be collected
# (taking its session with it) before the hook could stop it. `stop()` removes
# the entry, so nothing is retained longer than the session it protects.
_LIVE_CAMERAS: "set[AVFCamera]" = set()


@atexit.register
def _stop_live_cameras() -> None:
    for camera in list(_LIVE_CAMERAS):
        try:
            camera.stop()
        except Exception:  # nothing useful left to do this late in shutdown
            pass


class CameraError(RuntimeError):
    """Raised when the camera cannot be opened or delivers no frames."""


class CameraNotStarted(CameraError):
    """Raised when reading a camera that is not running.

    Distinct from a bad frame: callers retry a bad frame, but retrying this
    would spin forever.
    """


def _frame_from_pixel_buffer(pixel_buffer: Any, quartz: Any) -> np.ndarray:
    """Copy a locked BGRA ``CVPixelBuffer`` into a contiguous BGR array.

    The caller must already hold the read lock. Rows are padded to
    ``bytesPerRow``, which is not always ``width * 4``, so the padding is sliced
    off rather than assumed away.
    """

    width = int(quartz.CVPixelBufferGetWidth(pixel_buffer))
    height = int(quartz.CVPixelBufferGetHeight(pixel_buffer))
    stride = int(quartz.CVPixelBufferGetBytesPerRow(pixel_buffer))
    base = quartz.CVPixelBufferGetBaseAddress(pixel_buffer)
    if base is None or width <= 0 or height <= 0:
        raise CameraError("Camera delivered an empty pixel buffer")

    length = stride * height
    # PyObjC hands back an `objc.varlist` for a void* base address, which has no
    # length of its own. `as_buffer` is what turns it into readable memory.
    if hasattr(base, "as_buffer"):
        base = base.as_buffer(length)
    raw = np.frombuffer(base, dtype=np.uint8, count=length)
    rows = raw.reshape(height, stride)
    pixels = rows[:, : width * BGRA_CHANNELS].reshape(height, width, BGRA_CHANNELS)
    # BGRA -> BGR. `copy` is what makes this safe: it detaches the data from the
    # CoreVideo buffer before the delegate returns and the buffer is recycled.
    return np.ascontiguousarray(pixels[:, :, :3])


_DELEGATE_CLASS: Any = None


def _delegate_class() -> Any:
    """Build the ObjC delegate class once and cache it.

    An ObjC class name may only be registered once per process, so this cannot
    be defined inside ``start()`` — a second ``start()`` would fail to register.
    """

    global _DELEGATE_CLASS
    if _DELEGATE_CLASS is not None:
        return _DELEGATE_CLASS

    import CoreMedia
    import objc
    import Quartz
    from Foundation import NSObject

    class FrameDelegate(NSObject):
        """Receives frames on the camera queue. Copies, then publishes."""

        def initWithCamera_(self, camera_ref: "AVFCamera") -> Any:
            self = objc.super(FrameDelegate, self).init()
            if self is None:
                return None
            self._camera = camera_ref
            return self

        def captureOutput_didOutputSampleBuffer_fromConnection_(
            self, _output: Any, sample_buffer: Any, _connection: Any
        ) -> None:
            pixel_buffer = CoreMedia.CMSampleBufferGetImageBuffer(sample_buffer)
            if pixel_buffer is None:
                return
            flags = Quartz.kCVPixelBufferLock_ReadOnly
            if Quartz.CVPixelBufferLockBaseAddress(pixel_buffer, flags) != 0:
                return
            try:
                frame = _frame_from_pixel_buffer(pixel_buffer, Quartz)
            except Exception as exc:  # never let an exception cross into ObjC
                self._camera._publish_error(f"{type(exc).__name__}: {exc}")
                return
            finally:
                Quartz.CVPixelBufferUnlockBaseAddress(pixel_buffer, flags)
            self._camera._publish(frame)

    _DELEGATE_CLASS = FrameDelegate
    return _DELEGATE_CLASS


class AVFCamera:
    """An AVFoundation capture session that publishes BGR numpy frames.

    Mirrors the slice of ``cv2.VideoCapture`` this project actually used:
    ``start``/``read``/``stop`` plus ``is_open``.
    """

    def __init__(self, unique_id: str = "", *, name: str = "") -> None:
        self.unique_id = unique_id
        self.name = name
        self._lock = threading.Condition()
        self._frame: np.ndarray | None = None
        self._sequence = 0
        self._seen = 0
        self._error: str | None = None
        self._session: Any = None
        self._output: Any = None
        self._delegate: Any = None
        self._queue: Any = None
        self._input: Any = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._session is not None:
            return

        import AVFoundation as avf
        import libdispatch
        import Quartz

        camera = self._resolve_device(avf)
        delegate = _delegate_class().alloc().initWithCamera_(self)
        if delegate is None:
            raise CameraError("Could not create the capture delegate")

        session = avf.AVCaptureSession.alloc().init()
        device_input, error = avf.AVCaptureDeviceInput.deviceInputWithDevice_error_(
            camera, None
        )
        if device_input is None:
            raise CameraError(f"Could not open camera {self.name or self.unique_id!r}: {error}")
        if not session.canAddInput_(device_input):
            raise CameraError(f"Camera {self.name or self.unique_id!r} refused the capture input")
        session.addInput_(device_input)

        output = avf.AVCaptureVideoDataOutput.alloc().init()
        output.setVideoSettings_(
            {Quartz.kCVPixelBufferPixelFormatTypeKey: Quartz.kCVPixelFormatType_32BGRA}
        )
        # Drop stale frames rather than queueing them: the tracker only ever
        # wants the newest one, and a backlog is latency, not value.
        output.setAlwaysDiscardsLateVideoFrames_(True)
        if not session.canAddOutput_(output):
            raise CameraError("Camera refused the video data output")
        session.addOutput_(output)

        # Attach the delegate last. Anything above can still raise, and a
        # delegate attached to a session we then abandon is exactly the dangling
        # callback this class exists to avoid.
        queue = libdispatch.dispatch_queue_create(b"fifa4all.camera", None)
        output.setSampleBufferDelegate_queue_(delegate, queue)

        # Keep every strong reference alive for the session's lifetime. If the
        # delegate or queue is collected while the session runs, the callback
        # fires into freed memory.
        self._delegate = delegate
        self._queue = queue
        self._output = output
        self._input = device_input
        self._session = session
        _LIVE_CAMERAS.add(self)
        session.startRunning()

    def stop(self) -> None:
        """Tear the session down. Safe to call more than once."""

        session, output, queue = self._session, self._output, self._queue
        device_input = self._input
        self._session = None
        self._output = None
        self._input = None
        if session is not None:
            session.stopRunning()
            # Detach the output from the session outright. Clearing the delegate
            # alone leaves the session able to enqueue one more render block,
            # which is the window the drain below cannot close.
            if output is not None:
                session.removeOutput_(output)
            if device_input is not None:
                session.removeInput_(device_input)
        if output is not None:
            # Detach before dropping the delegate, so no *new* callback can
            # arrive after the object it calls into is gone.
            output.setSampleBufferDelegate_queue_(None, None)
        if queue is not None:
            # Clearing the delegate does not wait for callbacks AVFoundation has
            # already dispatched. One of those landing after the interpreter
            # starts shutting down segfaults in `PyGILState_Ensure`. The camera
            # queue is serial, so an empty block that runs to completion proves
            # every earlier block has finished.
            self._drain(queue)
        self._delegate = None
        self._queue = None
        _LIVE_CAMERAS.discard(self)
        with self._lock:
            self._frame = None
            # Do not let a dead session's error surface on the next one.
            self._error = None
            self._lock.notify_all()

    @staticmethod
    def _drain(queue: Any) -> None:
        """Block until every block already on `queue` has finished."""

        import libdispatch

        libdispatch.dispatch_sync(queue, lambda: None)

    @property
    def is_open(self) -> bool:
        return self._session is not None and bool(self._session.isRunning())

    # -- frames ------------------------------------------------------------

    def read(self, timeout: float = 5.0) -> tuple[bool, np.ndarray | None]:
        """Return the next frame that has not been read yet.

        Blocks until a fresh frame arrives or `timeout` elapses, so callers
        always get a new image rather than the same one twice.
        """

        if self._session is None:
            raise CameraNotStarted("Camera is not started")
        with self._lock:
            if self._sequence == self._seen:
                self._lock.wait(timeout)
            if self._error is not None:
                error, self._error = self._error, None
                # Consume the failed frame too. Leaving `_seen` behind would
                # hand the previous image back as if it were new.
                self._seen = self._sequence
                raise CameraError(f"Camera capture failed: {error}")
            if self._sequence == self._seen or self._frame is None:
                return False, None
            self._seen = self._sequence
            return True, self._frame

    def _publish(self, frame: np.ndarray) -> None:
        with self._lock:
            self._frame = frame
            self._sequence += 1
            self._lock.notify_all()

    def _publish_error(self, message: str) -> None:
        with self._lock:
            self._error = message
            self._sequence += 1
            self._lock.notify_all()

    # -- device selection --------------------------------------------------

    def _resolve_device(self, avf: Any) -> Any:
        if self.unique_id:
            device = avf.AVCaptureDevice.deviceWithUniqueID_(self.unique_id)
            if device is not None:
                return device
        if self.name:
            for device in avf.AVCaptureDevice.devicesWithMediaType_("vide"):
                if str(device.localizedName()) == self.name:
                    return device
        raise CameraError(
            f"No AVFoundation camera matched unique_id={self.unique_id!r} name={self.name!r}"
        )
