# FIFA4ALL

Play EA Sports FC on Amazon Luna with your face or your hand instead of a controller. Look with your head (or move your palm) for WASD, open your mouth or an open palm to shoot (Space hold after 200ms), wink or hold two fingers up to pass (L hold after 200ms, same as shoot). Hand and face auto-swap: a hand clearly in the MacBook camera takes over; otherwise face controls stay active. No toggle.

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

`--preview` waits until the orientation UI is listening, then opens **http://127.0.0.1:8765/** (Welcome / onboarding) with macOS `/usr/bin/open`. The live HUD camera is a large **color** MJPEG face feed (not grayscale) with the look-axis reticle, including the outer follow ring. The look-axis overlay is a **separate** camera window (`FIFA4ALL look axis`): mirrored MacBook frame, look-axis reticle, inner deadzone, outer follow ring, current keys, orange **RESET**, the **FIXED / FOLLOW** deadzone switch, and the active source (**FACE** / **HAND**, with the **PALM** point in hand mode). Website chrome stays in the browser; it is not drawn on the camera overlay. You do not need `npm run dev`. There is no Face/Hand button — the overlay only reports which source auto-swap picked.

To inject without opening a browser (keeps Luna focused):

```bash
MPLCONFIGDIR=.cache/matplotlib python -m tracking.live --no-preview
```

Lost face tracking releases every held key. Dropping a hand while it was the active source also releases, then face resumes if a face is still in frame.

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
4. Sit straight. Recentre from the site (**Find your center**, **Reset center**) or by tapping **RESET** on the look-axis overlay. **Eyebrow-raise recenter is temporarily disabled** (`EYEBROW_RECENTRE = False` in `tracking/controls.py`) so a look cannot be mistaken for a brow reset. Flip that flag to True to restore it. Keep the process running when you switch from the site to the match.
5. Look, open your mouth, or wink — or raise a hand. Holds stay down until you return to center / close the gesture. Switching between face and hand is automatic and releases any key the other source was holding.

| Gesture | Key (held) | In-game (simplified FC) |
| --- | --- | --- |
| Nose / head look axis, or palm / middle-of-hand (leave the center deadzone) | `W` `A` `S` `D` | Move |
| Mouth open, or all fingers open (open palm) | `Space` | Shoot (Space after the gesture stays detected 200ms; hold while it stays detected) |
| Wink (either eye; blinks rejected; a tilt-covered eye does not pass), or two fingers up (index + middle, others folded) | `L` | Pass (L after the gesture stays detected 200ms, same as shoot; hold while it stays detected) |
| Raised eyebrows | — | Temporarily disabled (does not recenter). Use overlay **RESET** or website **Find your center** / **Reset center**. |

The first valid nose point after start or Reset is the face joystick center. The first clear palm after start, Reset, or a new hand entering the frame is the hand joystick center. Combinations on one source are allowed (for example look + shoot). Face wink/mouth never fire in hand mode; hand gestures never fire in face mode.

### Auto-swap (face / hand)

MediaPipe Hands (same `mediapipe==0.10.14` stack as Face Mesh; not OpenPose) runs beside the face tracker. **Hand mode** starts when a hand is clearly in the MacBook frame (large enough, on-screen, confidently detected for a couple of frames). **Face mode** resumes when that hand leaves. There is no UI toggle and no website control for this.

- Movement uses the same inner deadzone (`enter_radius` 0.029 / `exit_radius` 0.040) and the same Follow outer ring (`follow_radius` 0.085). In hand mode the look-axis point is the palm (mean of wrist + finger bases), not the nose.
- Two fingers up = pass (`L`, 200ms hold delay). Open palm = shoot (`Space`, 200ms hold delay).
- Auto-swap clears expression latches so a face wink cannot leave `L` held after a hand takes over, and an open palm cannot leave `Space` held after the hand drops.
- Overlay **RESET** and website **Find your center** / **Reset center** still recapture the active source. The next nose and the next palm each get a fresh center. Eyebrow recenter stays off.

### Nose deadzone modes

WASD uses a nose deadzone. Two modes are available; **fixed center is the default** so existing play does not change until you switch.

| Mode | Behaviour | How to stop |
| --- | --- | --- |
| **Fixed center** (default) | The deadzone stays around the last calibrated center (start, **Find your center**, **Reset center**, overlay **RESET**). | Return into that original zone to release WASD. |
| **Follow** | Two radii. The inner deadzone still releases WASD. An **outer ring** sits beyond the WASD chips. The interface / deadzone center is pulled only when the nose is in that outer region (the center slides so the nose stays on the outer circle). Between the inner deadzone and the outer ring, the current WASD direction stays held. A held look does **not** auto-recentre after a few seconds. | Return into the inner deadzone. A small move back from the outer edge still moves the character. Recentre with overlay **RESET** or website **Find your center** / **Reset center**. Eyebrow recenter is temporarily off. |

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

- **Shooting** waits 200ms after mouth-open or an open palm is detected (open/reset hysteresis still applies) before holding Space, so FIFA's charge does not start on a brief open. If the gesture ends before 200ms, Space is never pressed. After Space is down, a longer hold is a more powerful shot. Face calibration samples the resting mouth, because a mouth at rest does not read zero and a fixed threshold can latch Space open permanently.
- **Passing** accepts either eye, or two fingers up (index + middle). A blink is rejected by requiring the other eye to stay open. Face wink and the two-finger gesture never fire at the same time.
- **Auto-swap** picks hand when a hand is clearly in frame and face otherwise. The look-axis overlay shows **FACE** or **HAND** (and **PALM** in hand mode). Switching does not need a button and does not leave keys stuck.
- **Recentre** with overlay **RESET** or website **Find your center** / **Reset center**. **Eyebrow-raise recenter is temporarily disabled** (set `EYEBROW_RECENTRE` in `tracking/controls.py` to True to restore the brow-to-eyelid path). In **follow** mode a held look still does not snap the home center onto the current face. A new stable hand in frame sets its first palm point as center, the same way the first nose does.
- **Movement** releases every key when tracking is lost, so a lost face or dropped hand cannot leave the player running. The inner “do nothing” deadzone is `enter_radius` 0.029 / `exit_radius` 0.040 (was 0.045 / 0.062, about 35% smaller), so a shorter look starts WASD. In **fixed** deadzone mode, WASD releases when the nose (or palm) returns to the calibrated center zone. In **follow** mode, an outer ring (`follow_radius` 0.085, was 0.170) beyond the WASD chips is the only place that drags the zone; between that ring and the inner deadzone the current direction stays held. Switch **FIXED / FOLLOW** on the look-axis overlay; default is fixed. The website live HUD shows the same two rings on a larger color camera feed (the OpenCV look-axis window stays a separate overlay).
