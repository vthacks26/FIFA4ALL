# FIFA4ALL

Play EA Sports FC on Amazon Luna with your face instead of a controller. Look with your head for WASD, open your mouth to shoot (Space hold after 200ms), wink to pass (L hold).

This is a VTHacks accessibility hack. The live product on `main` injects macOS Quartz HID key holds into the focused app (Google Chrome running Luna).

## Run from scratch (macOS)

You need **macOS**, **Python 3.12**, a **MacBook camera**, and **Google Chrome** with Amazon Luna. Quartz key injection does not work on other OSes. Live capture opens only a built-in Mac camera (`MacBook Pro Camera` / FaceTime / built-in) and never an iPhone or Continuity Camera index.

Do not use the system `python` binary (it is often missing on macOS) and do not use Python 3.9 (MediaPipe / OpenCV will fail there — the usual error is `cv2` missing). Create a **3.12** venv so `python` and `pip` exist.

If `python3.12` is not on your PATH:

```bash
brew install python@3.12
```

### 1. Clone `main`

```bash
git clone https://github.com/vthacks26/FIFA4ALL.git
cd FIFA4ALL
git checkout main
git pull
```

If you already have a clone, skip `git clone` and still run `git checkout main` then `git pull` so you are on the live product.

### 2. Python 3.12 venv

From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r tracking/requirements.txt
```

`tracking/requirements.txt` installs `mediapipe==0.10.14`, `protobuf>=4.25.3,<5`, `opencv-python`, and `numpy`. Always run the live module from this root so `python -m tracking.live` resolves. `MPLCONFIGDIR=.cache/matplotlib` keeps MediaPipe’s Matplotlib config out of your home directory (that path is gitignored).

### 3. Camera and Accessibility

In **System Settings → Privacy & Security**, grant both to **Terminal** (or iTerm / the app that will run Python — not only Chrome):

- **Camera** — first run may prompt. Without this, the MacBook camera will not open.
- **Accessibility** — without this, Quartz HID holds may be dropped (`Accessibility is NOT granted; Quartz keys may be dropped.`).

### 4. Start

With the venv still active, from the repository root:

```bash
MPLCONFIGDIR=.cache/matplotlib python -m tracking.live --preview
```

`--preview` waits until the orientation UI is listening, then opens **http://127.0.0.1:8765/** (Welcome / onboarding) with macOS `/usr/bin/open`. The live HUD camera is a large **color** MJPEG face feed (not grayscale) with the look-axis reticle, including the outer follow ring. The look-axis overlay is a **separate** camera window (`FIFA4ALL look axis`): mirrored MacBook frame, face landmarks, WASD axis, inner deadzone, outer follow ring, current keys, orange **RESET**, and the **FIXED / FOLLOW** deadzone switch. Website chrome stays in the browser; it is not drawn on the camera overlay. You do not need `npm run dev`.

To inject without opening a browser (keeps Luna focused):

```bash
MPLCONFIGDIR=.cache/matplotlib python -m tracking.live --no-preview
```

`--no-preview` still serves http://127.0.0.1:8765/ and still sends keys; it does not raise a window. `--no-preview` wins if both flags are passed. Quit with **Ctrl+C**. Lost face tracking releases every held key.

### After you close Terminal

The venv deactivates when the shell exits. From the clone:

```bash
cd FIFA4ALL
source .venv/bin/activate
MPLCONFIGDIR=.cache/matplotlib python -m tracking.live --preview
```

You do not need to recreate `.venv` or reinstall unless you deleted it.

## Play on Luna

1. Grant Camera and Accessibility, then start `--preview` (orientation) or `--no-preview` (match, Luna already focused).
2. Open **Google Chrome** → Amazon Luna → EA Sports FC (simplified keyboard layout).
3. **Click the game** so Chrome / Luna is focused. OS keys go to the frontmost app.
4. Sit straight. Recentre by **raising your eyebrows**, from the site (**Find your center**, **Reset center**), or by tapping **RESET** on the look-axis overlay. Eyebrow raise, site calibrate, and overlay RESET all call the same `ControlStateMachine.calibrate` on this process — they apply to play. A held raise does not repeat the reset; opening your mouth to shoot does not reset. Keep the process running when you switch from the site to the match.
5. Look, open your mouth, or wink. Holds stay down until you return to center / close your mouth / stop winking.

| Gesture | Key (held) | In-game (simplified FC) |
| --- | --- | --- |
| Nose / head look axis (leave the center deadzone) | `W` `A` `S` `D` | Move |
| Mouth open | `Space` | Shoot (Space after the mouth stays open 200ms; hold while it stays open) |
| Wink (either eye; blinks rejected) | `L` | Pass (hold while the wink is detected) |
| Raised eyebrows | — | Recentre / recalibrate pose (same as overlay RESET and `POST /calibrate`) |

The first valid nose point after start or Reset is the joystick center. Combinations are allowed (for example look + shoot).

### Nose deadzone modes

WASD uses a nose deadzone. Two modes are available; **fixed center is the default** so existing play does not change until you switch.

| Mode | Behaviour | How to stop |
| --- | --- | --- |
| **Fixed center** (default) | The deadzone stays around the last calibrated center (start, eyebrows, **Find your center**, **Reset center**, overlay **RESET**). | Return into that original zone to release WASD. |
| **Follow** | Two radii. The inner deadzone still releases WASD. An **outer ring** sits beyond the WASD chips. The interface / deadzone center is pulled only when the nose is in that outer region (the center slides so the nose stays on the outer circle). Between the inner deadzone and the outer ring, the current WASD direction stays held. | Return into the inner deadzone. A small move back from the outer edge still moves the character. |

Switch at runtime from the look-axis overlay (`FIFA4ALL look axis`): tap **FIXED** or **FOLLOW** under **RESET**. That click changes `ControlStateMachine` on this process immediately, so the WASD keys Quartz is already injecting use the new deadzone. Recentre / calibrate still resets the center as today.

The onboarding website toggle still POSTs `/deadzone-mode` if you have that tab open; it is optional. The overlay switch is the one to use while tracking.

Optional startup flag (the overlay switch can still change it afterwards):

```bash
MPLCONFIGDIR=.cache/matplotlib python -m tracking.live --preview --deadzone-mode follow
```

**Exclusive fullscreen covers the overlay.** Press **Esc** if you need to see the look-axis HUD.

## Tests (no camera)

```bash
python -m unittest discover -s tests
```

The overlay annotate test imports OpenCV, so install `tracking/requirements.txt` first if that case errors on `cv2`.

More tracking notes: [`tracking/README.md`](tracking/README.md). Orientation screens: [`onboarding/README.md`](onboarding/README.md).

## Gesture notes

- **Shooting** waits 200ms after mouth-open is detected (open/reset hysteresis still applies) before holding Space, so FIFA's charge does not start on a brief open. If the mouth closes before 200ms, Space is never pressed. After Space is down, a longer open is a more powerful shot. Calibration samples the resting mouth, because a mouth at rest does not read zero and a fixed threshold can latch Space open permanently.
- **Passing** accepts either eye. A blink is rejected by requiring the other eye to stay open.
- **Recentre** by raising your eyebrows (or overlay **RESET** / website **Find your center**). Detection is the brow-to-eyelid gap above the resting value sampled on the first valid face and again on click-calibrate, so a normal open mouth used for shoot does not reset. The trigger is edge-latched: a held raise fires once until you lower your brows.
- **Movement** releases every key when tracking is lost, so a lost face cannot leave the player running. In **fixed** deadzone mode, WASD releases when the nose returns to the calibrated center zone. In **follow** mode, an outer ring beyond the WASD chips is the only place that drags the zone; between that ring and the inner deadzone the current direction stays held. Switch **FIXED / FOLLOW** on the look-axis overlay; default is fixed. The website live HUD shows the same two rings on a larger color camera feed (the OpenCV look-axis window stays a separate overlay).
