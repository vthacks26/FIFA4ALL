# Fix: Python segfaults during webcam capture

## Root cause

OpenCV's macOS AVFoundation backend races on its pixel buffer. `CaptureDelegate`
swaps `mCurrentImageBuffer` on the `cameraQueue` dispatch thread while the main
thread reads/locks that same buffer inside `read()`. No mutex protects the
handoff.

Evidence — six crash reports in `~/Library/Logs/DiagnosticReports`, 2026-09-19:

- 5x `SIGTRAP` in `CFRelease` on `cameraQueue`, inside
  `-[CaptureDelegate captureOutput:didOutputSampleBuffer:fromConnection:]`
- 1x `SIGSEGV` (`KERN_INVALID_ADDRESS` at 0x0) on the main thread in
  `CVPixelBufferLockBaseAddress` via `-[CaptureDelegate updateImage]`

In `Python-2026-09-19-144847.ips` the main thread is parked in
`-[CaptureDelegate grabImageUntilDate:]` — i.e. blocked inside
`self._capture.read()` at `tracking/mediapipe_tracker.py:145` — at the moment
the camera queue over-releases the buffer. Over-release -> SIGTRAP; freed or
NULL buffer -> SIGSEGV. Both signatures are the same defect.

Not fixable from Python. The fix is to stop routing camera buffers through
OpenCV on macOS.

## Approach

Own the AVFoundation capture session. The delegate copies the pixel buffer into
a numpy array **on the camera queue, while the buffer is provably alive**, then
publishes that array under a lock. No CoreVideo buffer lifetime ever crosses a
thread boundary, so the race cannot occur.

`tracking/mac_camera.py` already enumerates AVFoundation devices via raw
`objc_msgSend`. Subclassing an ObjC delegate that way is impractical, so the new
module uses PyObjC (`pyobjc-core` is already installed).

## Steps

- [x] 1. Add `pyobjc-framework-AVFoundation` to `tracking/requirements.txt` and
      install it -> verify: `import AVFoundation` succeeds in the venv
- [x] 2. Write `tracking/avf_camera.py`: `AVFCamera.start/read/stop`, delegate
      converts `CVPixelBuffer` -> BGR numpy on the camera queue under a lock;
      `read(timeout)` waits on a `Condition` -> verify: unit tests in step 4
- [x] 3. Wire `WebcamFaceTracker` to `AVFCamera` instead of `cv2.VideoCapture`;
      keep the public interface and device-selection behaviour unchanged; drop
      the `CAP_PROP_BUFFERSIZE` line (a no-op on this backend) -> verify: no
      call-site changes needed in `bridge/`, `tracking/live.py`, `tracking/diagnostic.py`
- [x] 4. Tests `tests/test_avf_camera.py`: pixel-buffer -> array conversion,
      stride/padding handling, `read()` timeout when no frame arrives, `read()`
      returns the newest frame, `stop()` is idempotent. Hardware-free via a fake
      buffer -> verify: `pytest tests/` green on a machine with no camera
- [x] 5. Smoke test against the real camera for longer than the ~10 min that
      previously crashed -> verify: no new `Python-*.ips` in DiagnosticReports

## Second defect, found by the smoke test

The first version of `avf_camera.py` still crashed — differently, and this one
was ours, not OpenCV's. `Python-2026-09-19-152544.ips`: `SIGSEGV` in
`PyGILState_Ensure` / `new_threadstate`, on our own `fifa4all.camera` queue.

Clearing the sample-buffer delegate does not wait for callbacks AVFoundation has
_already_ dispatched. One of those landing while the interpreter was shutting
down called into a dying thread state.

Fix: `stop()` now stops the session, detaches the delegate, then
`dispatch_sync`s an empty block on the camera queue. The queue is serial, so a
block that runs to completion proves every earlier block has finished. Only then
are the delegate and queue dropped. Locked in by
`test_stop_drains_the_camera_queue_after_detaching_the_delegate`.

Also reordered `start()` to attach the delegate only after the output is added
to the session, so a failure part-way through cannot leave a live delegate
attached to an abandoned session.

### The drain alone was not enough

`Python-2026-09-19-153103.ips` showed the same `PyGILState_Ensure` crash _after_
the drain was in place. Clearing the delegate does not stop the session from
enqueueing one more render block, and a block enqueued after our `dispatch_sync`
had already run was never drained.

Closed on two fronts:

- `stop()` now calls `removeOutput_` / `removeInput_` on the session before
  clearing the delegate, so the session has nothing left to render into. Full
  order: stop session -> remove output -> remove input -> clear delegate ->
  drain queue -> drop references.
- An `atexit` hook stops any camera still live at interpreter exit. Teardown
  then always happens while Python is fully alive, even if a caller forgets
  `stop()` or an error path skips it.

## Verification

- 163 tests pass, including 25 new hardware-free tests for the capture path.
- 40 open/read/stop/exit cycles under concurrent camera load: no crashes. The
  pre-`removeOutput_` version crashed roughly 1 in 20 of the same cycles.
- 12 minute end-to-end soak through `WebcamFaceTracker`: 21,508 frames, 0 missed
  reads, 29.9 fps, no new crash report. The original crashes came every ~10 min.
- Channel order confirmed by eye on a saved frame — a red tile wall renders red,
  so the BGRA -> BGR slice is right and MediaPipe receives correct colours.

Note: crash reports are written to `~/Library/Logs/DiagnosticReports` with a
lag. An early "clean" reading here was wrong because it sampled too soon; allow
time before concluding a run was crash-free.

## Out of scope (mentioned, not changed)

- `opencv-python` and `opencv-contrib-python` 4.11.0.86 are both installed and
  overwrite each other's `cv2`. Only `opencv-python` is in requirements.txt.
  Real config hazard, unrelated to this crash.
