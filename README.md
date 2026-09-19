# FIFA4ALL

Play EA Sports FC on Amazon Luna with your face instead of a controller. Look with your head for WASD, open your mouth to shoot (Space hold), wink to pass (L hold).

This is a VTHacks accessibility hack. The live path in this branch injects macOS Quartz HID key holds into the focused app (Google Chrome running Luna).

## Requirements

- macOS (Quartz `CGEventPost` key injection only works here)
- Built-in **MacBook Pro Camera** (FaceTime / built-in Mac camera). Live capture **never** opens iPhone or Continuity Camera indexes.
- Google Chrome with Amazon Luna, EA Sports FC in the simplified keyboard layout
- Python 3.12 (MediaPipe `0.10.14` is pinned for 3.12; 3.14 is not a reliable runtime for this stack)
- Camera **and** Accessibility permission for Terminal / Python (see [Permissions](#permissions))

## Install

From a clone of [vthacks26/FIFA4ALL](https://github.com/vthacks26/FIFA4ALL):

```bash
git checkout cursor/tracking-quartz-live-a2a3

python3.12 -m venv .venv-mediapipe
source .venv-mediapipe/bin/activate
python -m pip install -r tracking/requirements.txt
```

`tracking/requirements.txt` is the webcam runtime: `mediapipe==0.10.14`, `opencv-python`, and `numpy`. On Apple Silicon you can create the venv with Homebrew Python 3.12 instead:

```bash
brew install python@3.12
/opt/homebrew/bin/python3.12 -m venv .venv-mediapipe
```

Always run the live module from the **repository root** so `python -m tracking.live` resolves. `MPLCONFIGDIR=.cache/matplotlib` keeps MediaPipe’s Matplotlib config out of your home directory (that path is gitignored).

## Run

Preview overlay (face, look-axis, live keys, Reset):

```bash
MPLCONFIGDIR=.cache/matplotlib python -m tracking.live --preview
```

Headless inject (same mapping, no overlay window):

```bash
MPLCONFIGDIR=.cache/matplotlib python -m tracking.live --no-preview
```

`--no-preview` wins if both flags are passed. Quit with **Ctrl+C**. Lost face tracking releases every held key.

Do not start this from another directory, and do not point OpenCV at Continuity Camera. The process enumerates AVFoundation devices by name and opens only a built-in Mac camera (`MacBook Pro Camera` / FaceTime / built-in). If index `0` is an iPhone, that index is skipped.

## Play on Luna

1. Grant Camera and Accessibility (below), then start `--preview` or `--no-preview`.
2. Open **Google Chrome** → Amazon Luna → EA Sports FC.
3. **Click the game** so Chrome / Luna is focused. OS keys go to the frontmost app; if Chrome is not frontmost, the injector warns and keys will land somewhere else.
4. Sit straight in frame. Tap the orange **RESET** on the `FIFA4ALL look axis` overlay (preview mode) so the next valid face pose is neutral.
5. Look, open your mouth, or wink. Holds stay down until you return to center / close your mouth / stop winking.

### Mappings

| Gesture | Key (held) | In-game (simplified FC) |
| --- | --- | --- |
| Nose / head look axis (leave the center deadzone) | `W` `A` `S` `D` | Move |
| Mouth open | `Space` | Shoot (hold while the mouth stays open) |
| Left wink | `L` | Pass (hold while the wink is detected) |

The first valid nose point after start or Reset is the joystick center. Returning to that center releases WASD. Combinations are allowed (for example look + shoot).

### Overlay

`--preview` opens a floating, non-activating window titled **`FIFA4ALL look axis`**. It shows the MacBook camera frame, face landmarks, the WASD look-axis, current keys, and an orange **RESET** control (plus a real AppKit Reset button on the window). Sit straight, then tap **RESET** to clear the pose baseline and recapture neutral.

The overlay is meant to stay above Luna without stealing key focus. **Exclusive fullscreen still covers it.** Press **Esc** to leave exclusive fullscreen if you need to see Reset or the look-axis HUD.

## Permissions

In **System Settings → Privacy & Security**:

- **Camera** — allow Terminal (or iTerm / your Python host) so the MacBook camera can open. The first run may prompt.
- **Accessibility** — allow the same Terminal / Python process. Without it, Quartz HID holds may be dropped (`Accessibility is NOT granted; Quartz keys may be dropped.`).

Grant these to the process that actually runs `python -m tracking.live`, not only to Chrome.

## Tests (no camera)

Mapping, camera-name selection, and Reset geometry tests do not open the webcam:

```bash
python -m unittest discover -s tests
```

The overlay annotate test imports OpenCV, so install `tracking/requirements.txt` first if that case errors on `cv2`.

## Related commands in this repo

These exist but are **not** the Luna injector:

| Command | What it does |
| --- | --- |
| `MPLCONFIGDIR=.cache/matplotlib python -m tracking.control_preview` | Same suggested labels; **does not** send keys. Press `q` to quit, `r` to reset the nose center. |
| `MPLCONFIGDIR=.cache/matplotlib python -m tracking.diagnostic` | Webcam feature overlay. Press `q` to quit. |
| `python -m tracking.haar_control_preview` | Lighter OpenCV nose fallback (WASD preview only; no mouth/wink, no Quartz inject). |

More tracking notes: [`tracking/README.md`](tracking/README.md).
