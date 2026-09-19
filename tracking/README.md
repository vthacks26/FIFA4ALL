# Tracking

Person 1 owns this package. It produces local webcam movement measurements for calibration and controls without assigning game actions, calibrating users, or sending inputs.

## Shared Contract Status

The repository did not yet contain Person 3's canonical `shared/` interfaces when this package was created. `tracking.frames.MovementFrame` follows the agreed minimal shape so the pipeline can move forward:

- `timestamp_monotonic`: seconds from a monotonic clock.
- `tracking_valid`: `False` when face tracking is lost or required landmarks are unavailable.
- `features`: named measurements. Missing values are `available=False` and `value=None`; they are never replaced with zero.

Once `shared.MovementFrame` is published, adapt the boundary in one place instead of changing feature names or units.

## Features

| Feature            | Unit                  | Sign and meaning                                                                                                                                          | Limitations                                                                                                                                           |
| ------------------ | --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mouth_opening`    | `ratio`               | Vertical upper-lip to lower-lip distance divided by cheek-to-cheek face width. Larger positive values mean a more open mouth.                             | Sensitive to lip occlusion, facial hair, facial expression, and large head turns.                                                                     |
| `head_turn`        | `normalized_x_offset` | Nose-tip x offset from cheek midpoint divided by face width. Positive means the nose moved toward the user's right in the camera image.                   | Coarse 2D proxy, not true yaw. Camera angle and face shape affect values.                                                                             |
| `head_tilt`        | `degrees`             | Eye-line angle. Positive means the user's right eye appears lower in the camera image.                                                                    | Assumes the camera is roughly level. Glasses, hair, and occlusion can affect landmarks.                                                               |
| `left_wink`        | `ratio_delta`         | Right-eye openness minus left-eye openness, normalized by face width. Larger positive values mean the user's left eye appears more closed than the right. | Rough diagnostic only. Sensitive to glasses, shadows, eye shape, camera angle, and partial occlusion.                                                 |
| `head_pitch`       | `normalized_y_offset` | Nose-tip y offset below the eye line divided by face width. Larger means the chin dropped toward the chest.                                               | Proxy, not an angle. Moves if the user slides up or down in their seat. Shrinks by cos(roll).                                                         |
| `brow_raise`       | `ratio`               | Mean brow-to-eye vertical gap divided by face width, averaged over both sides. Larger means the brows are raised.                                         | Resting value varies with brow shape and glasses frames, so it must be compared against a per-user sample. Head pitch moves it by several percent.    |
| `mouth_width`      | `ratio`               | Mouth-corner separation divided by face width. Larger means a wider smile.                                                                                | Head yaw makes it read narrower than it is, which loses smiles but cannot invent one. A jaw drop narrows it slightly.                                 |
| `mouth_pucker`     | `ratio`               | Lip gap divided by mouth-corner separation: the aperture's aspect ratio. Larger means a rounder "O".                                                      | Cannot separate a pucker from a small jaw drop; both raise it, from opposite ends of the fraction. Lip protrusion is out-of-plane and invisible here. |
| `jaw_lateral`      | `normalized_x_offset` | Chin offset from the nose tip projected onto the eye line, divided by face width. Positive means the chin slid toward the user's right in the image.      | Head roll cancels by construction; head yaw does not, and leaves a residual offset in the direction of the turn.                                      |
| `cheek_span_ratio` | `ratio`               | Cheek-to-cheek distance divided by inter-eye distance.                                                                                                    | A cheek puff moves it by only a percent or two, about what head yaw moves it. Weak diagnostic, not a trigger.                                         |

The three optional landmark groups behind `brow_raise`, the mouth-corner
features, and `jaw_lateral` are not required: a tracker that does not emit
them yields `available=False` for those features and a valid frame for the
rest.

Do not equate landmark confidence with gesture reliability. Calibration must still ask the user what is comfortable.

## Setup on macOS

Core feature calculation and synthetic fixtures use only the Python standard library.

For the optional webcam diagnostic, from the repository root:

```bash
brew install python@3.12
/opt/homebrew/bin/python3.12 -m venv .venv-mediapipe
. .venv-mediapipe/bin/activate
python -m pip install -r tracking/requirements.txt
```

Coordinate dependency versions with Person 3 before moving these into the project-level dependency configuration.
See `tracking/DEPENDENCIES.md` for the lightweight dependency split Person 3 can use.

## Diagnostic

Run:

```bash
MPLCONFIGDIR=.cache/matplotlib python -m tracking.diagnostic
```

The diagnostic opens a webcam preview, overlays live feature values, shows tracking status, and reports measured processing rate. Press `q` to quit. The camera is released on normal exit.

For Quartz OS key holds into the frontmost app (Google Chrome / Luna), MacBook camera only.

Face + WASD look-axis overlay (non-activating, not click-through). Sit straight and tap the **Reset** button on the look-axis window to recapture the neutral nose axis:

```bash
MPLCONFIGDIR=.cache/matplotlib python -m tracking.live --preview
```

Headless inject (no overlay):

```bash
MPLCONFIGDIR=.cache/matplotlib python -m tracking.live --no-preview
```

This uses the same nose-joystick / mouth-Space-hold / wink-L mapping as the preview, posted via `CGEventPost(kCGHIDEventTap)`.

For a live control-label preview that does not send keyboard input:

```bash
MPLCONFIGDIR=.cache/matplotlib python -m tracking.control_preview
```

It displays suggested labels only:

- nose leaves the center deadzone screen-left/screen-right: `D` / `A`
- nose leaves the center deadzone up/down: `W` / `S`
- mouth open: `Space`
- left wink: `L`

The MediaPipe preview acts like a virtual joystick: the first valid nose point is neutral, returning to center means no movement, and pressing `r` resets the neutral center.

`Space` remains active while the mouth stays above the open threshold. The preview also shows `space hold` seconds and a capped charge percentage so the input adapter can later translate a longer mouth-open hold into a longer in-game shot press.

These are temporary preview labels for tracking validation. Person 3 still owns real input adapters and action assignment.

On macOS, live capture enumerates AVFoundation devices by name and opens only `MacBook Pro Camera` / FaceTime / built-in. It never opens or probes iPhone or Continuity Camera indexes — if OpenCV index `0` is the phone, that index is skipped. The first run may trigger a camera permission prompt for the Mac camera only. Grant camera access to the terminal or Codex host in System Settings, then rerun the command.

If MediaPipe is unavailable on a teammate's Mac, use the lighter OpenCV nose fallback:

```bash
python -m tracking.haar_control_preview
```

The fallback previews only nose movement: forward is no key, nose left/right is `A`/`D`, and nose up/down is `W`/`S`. Mouth and wink are unavailable there; use the MediaPipe preview for those once the model/runtime works on that Mac.

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
