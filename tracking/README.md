# Tracking

Person 1 owns this package. It produces local webcam movement measurements for calibration and controls without assigning game actions, calibrating users, or sending inputs.

## Shared Contract Status

The repository did not yet contain Person 3's canonical `shared/` interfaces when this package was created. `tracking.frames.MovementFrame` follows the agreed minimal shape so the pipeline can move forward:

- `timestamp_monotonic`: seconds from a monotonic clock.
- `tracking_valid`: `False` when face tracking is lost or required landmarks are unavailable.
- `features`: named measurements. Missing values are `available=False` and `value=None`; they are never replaced with zero.

Once `shared.MovementFrame` is published, adapt the boundary in one place instead of changing feature names or units.

## Features

| Feature | Unit | Sign and meaning | Limitations |
| --- | --- | --- | --- |
| `mouth_opening` | `ratio` | Vertical upper-lip to lower-lip distance divided by cheek-to-cheek face width. Larger positive values mean a more open mouth. | Sensitive to lip occlusion, facial hair, facial expression, and large head turns. |
| `head_turn` | `normalized_x_offset` | Nose-tip x offset from cheek midpoint divided by face width. Positive means the nose moved toward the user's right in the camera image. | Coarse 2D proxy, not true yaw. Camera angle and face shape affect values. |
| `head_tilt` | `degrees` | Eye-line angle. Positive means the user's right eye appears lower in the camera image. | Assumes the camera is roughly level. Glasses, hair, and occlusion can affect landmarks. |
| `left_wink` | `ratio_delta` | Right-eye openness minus left-eye openness, normalized by face width. Larger positive values mean the user's left eye appears more closed than the right. | Rough diagnostic only. Sensitive to glasses, shadows, eye shape, camera angle, and partial occlusion. |

Do not equate landmark confidence with gesture reliability. Calibration must still ask the user what is comfortable.

## Setup on macOS

Core feature calculation and synthetic fixtures use only the Python standard library.

For the optional webcam diagnostic, from the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r tracking/requirements.txt
```

Coordinate dependency versions with Person 3 before moving these into the project-level dependency configuration.
See `tracking/DEPENDENCIES.md` for the lightweight dependency split Person 3 can use.

## Diagnostic

Run:

```bash
python -m tracking.diagnostic
```

The diagnostic opens a webcam preview, overlays live feature values, shows tracking status, and reports measured processing rate. Press `q` to quit. The camera is released on normal exit.

For a live control-label preview that does not send keyboard input:

```bash
python -m tracking.control_preview
```

It displays suggested labels only:

- head turn left/right: `A` / `D`
- head tilt up/down: `W` / `S`
- mouth open: `Space`
- left wink: `L`

These are temporary preview labels for tracking validation. Person 3 still owns real input adapters and action assignment.

On macOS, the first run may trigger a camera permission prompt. If the preview cannot open camera index `0`, grant camera access to the terminal or Codex host in System Settings, then rerun the command.

If MediaPipe is unavailable on a teammate's Mac, use the lighter OpenCV fallback:

```bash
python -m tracking.haar_control_preview
```

The fallback previews head movement with a face box and a rough open-mouth score. Wink is marked unavailable there; use the MediaPipe preview for wink once the model/runtime works on that Mac.

Testing notes to record on each teammate Mac:

- Mac model and macOS version.
- Whether the webcam permission prompt appeared and was accepted.
- Lighting conditions.
- Camera angle and distance.
- Occlusions such as glasses, mask, hand, hair, headset, or microphone.
- Observed processing rate.
- Any tracking loss or unstable values.

No video is recorded by default.

## Synthetic Fixtures

Use `tracking.synthetic.synthetic_sequence(name)` for simulation without Luna, an Amazon account, or a webcam. Available sequences:

- `rest`
- `intentional_movement`
- `small_movement`
- `jitter`
- `tracking_loss`
- `recovery`

## Tests

The current tests validate feature calculations from controlled landmarks and synthetic tracking-loss behavior:

```bash
python -m unittest
```
