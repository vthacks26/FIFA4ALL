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
python3.12 -m venv .venv-mediapipe
source .venv-mediapipe/bin/activate
python -m pip install -r tracking/requirements.txt
```

`tracking/requirements.txt` is the webcam runtime: `mediapipe==0.10.14`, `protobuf>=4.25.3,<5` (Face Mesh still uses `GetPrototype`; protobuf 5+ removed it), `opencv-python`, and `numpy`. On Apple Silicon you can create the venv with Homebrew Python 3.12 instead:

```bash
brew install python@3.12
/opt/homebrew/bin/python3.12 -m venv .venv-mediapipe
```

Always run the live module from the **repository root** so `python -m tracking.live` resolves. `MPLCONFIGDIR=.cache/matplotlib` keeps MediaPipe’s Matplotlib config out of your home directory (that path is gitignored).

## Run

One process starts Quartz inject and the orientation website. With `--preview` it waits until that UI is **listening**, then opens the Welcome page and shows a **separate** native camera overlay. On macOS this uses `/usr/bin/open http://127.0.0.1:8765/` (Python's `webbrowser.open` often no-ops and never raises a window). If open fails, the process prints a line with that URL so you can click it. You do **not** need `npm run dev`. The two UIs stay split: website chrome never moves into the look-axis window.

```bash
MPLCONFIGDIR=.cache/matplotlib python -m tracking.live --preview
```

That auto-opens **http://127.0.0.1:8765/** — Welcome, then the pushed onboarding / practice / live-telemetry flow (`WELCOME` → drills → `LIVE_TELEMETRY`). Same process serves every later orientation route from that origin. Pull this branch before retrying if `--preview` only printed that it was running.

Headless inject (same mapping and UI server, **no** overlay and **no** browser — so Luna can keep keyboard focus):

```bash
MPLCONFIGDIR=.cache/matplotlib python -m tracking.live --no-preview
```

`--no-preview` still serves http://127.0.0.1:8765/ ; open it yourself only when you are not mid-match. `--no-preview` wins if both flags are passed. Quit with **Ctrl+C**. Lost face tracking releases every held key.

Do not start this from another directory, and do not point OpenCV at Continuity Camera. The process enumerates AVFoundation devices by name and opens only a built-in Mac camera (`MacBook Pro Camera` / FaceTime / built-in). If index `0` is an iPhone, that index is skipped.

## Play on Luna

1. Grant Camera and Accessibility (below), then start `--preview` (demo / orientation) or `--no-preview` (match, Luna already focused).
2. On `--preview`, go through the website flow that just opened. When you are ready to play, open **Google Chrome** → Amazon Luna → EA Sports FC.
3. **Click the game** so Chrome / Luna is focused. OS keys go to the frontmost app; if Chrome is not frontmost, the injector warns and keys will land somewhere else.
4. Sit straight. Recentre from the website (**Find your center**, then **Reset center** on the live HUD) or tap **RESET** on the look-axis overlay. Both hit the same live session.
5. Look, open your mouth, or wink. Holds stay down until you return to center / close your mouth / stop winking.

Positioning on the website (SSE) and **RESET / calibrate** stay live for the whole process. **Find your center**, **Reset center**, and overlay **RESET** all call `POST /calibrate` on this same process. That recentres the one tracker that injects WASD / Space / L into Luna — there is no second live session. Keep the process running when you switch from the website to the match.

### Mappings

| Gesture | Key (held) | In-game (simplified FC) |
| --- | --- | --- |
| Nose / head look axis (leave the center deadzone) | `W` `A` `S` `D` | Move |
| Mouth open | `Space` | Shoot (hold while the mouth stays open) |
| Wink (either eye; blinks rejected) | `L` | Pass (hold while the wink is detected) |

The first valid nose point after start or Reset is the joystick center. Returning to that center releases WASD. Combinations are allowed (for example look + shoot).

### Two windows (they stay separate)

`--preview` opens **two** UIs. They are not combined:

| Window | What it is |
| --- | --- |
| Default browser → **http://127.0.0.1:8765/** | Orientation website: Welcome, controls, Find your center, practice drills, live telemetry, **Reset center**. Website chrome lives only here. macOS `--preview` launches this with `/usr/bin/open` after the UI is listening. |
| Native **`FIFA4ALL look axis`** | Camera / vision overlay only: mirrored MacBook frame, face landmarks, WASD look-axis, current keys, orange **RESET**. No onboarding chrome. |

`--no-preview` does not open a browser, because raising a window would steal keyboard focus from Luna.

The overlay is meant to stay above Luna without stealing key focus. **Exclusive fullscreen still covers it.** Press **Esc** to leave exclusive fullscreen if you need to see the look-axis HUD.

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

More tracking notes: [`tracking/README.md`](tracking/README.md). Orientation screens: [`onboarding/README.md`](onboarding/README.md).

## One product

`python -m tracking.live` is the only match path. The same process owns the
MacBook camera, Quartz HID holds, the look-axis overlay + RESET, and the
orientation website at http://127.0.0.1:8765/ . `--preview` waits until that
server answers `GET /`, then on macOS runs `/usr/bin/open` on the Welcome URL
and keeps the camera overlay as a separate vision window. Do not start
`bridge.server` or `npm run dev` for a match — that would be a second,
disconnected stack.

```bash
MPLCONFIGDIR=.cache/matplotlib python -m tracking.live --preview
# inject + UI server, no overlay and no browser (keeps Luna focused):
MPLCONFIGDIR=.cache/matplotlib python -m tracking.live --no-preview
```

`python -m bridge.server --mock` is UI-only with no camera. `python -m
bridge.server` without `--mock` is an alias of `tracking.live --no-preview`.

## Permissions

Keyboard output needs macOS Accessibility permission. Without it macOS discards
injected events silently, which is the usual reason keys never reach Luna.
Check before a demo:

```bash
python3 -m output.selftest
```

It needs no virtualenv and no third-party packages. `PASS` means synthetic keys
reach the same input stack Luna reads from.

## Gesture notes

- **Shooting** holds Space while the mouth is open, so a longer open is a more
  powerful shot. Calibration samples the resting mouth, because a mouth at rest
  does not read zero and a fixed threshold can latch Space open permanently.
- **Passing** accepts either eye. A blink is rejected by requiring the other eye
  to stay open: eyelids do not close in sync, so mid-blink the left/right
  difference briefly doubles the wink threshold.
- **Movement** releases every key when tracking is lost, so a lost face cannot
  leave the player running.
