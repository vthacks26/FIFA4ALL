# FIFA4ALL Orientation (second monitor)

The onboarding, calibration and live-telemetry experience that runs on Monitor 2
while EA Sports FC plays on Monitor 1 via Amazon Luna.

Source of truth for the design is `vthacks26-onboarding.zip`: `BRAND_KIT.md`,
`ORIENTATION_FLOW.md`, `TECHNICAL_SPEC.md`, `AGENT_HANDOFF.md`.

## Architecture

```text
webcam -> tracking/mediapipe_tracker.py   (MediaPipe face landmarks)
       -> tracking/features.py            (smoothed geometric features)
       -> tracking/controls.py            (dead zone, 8 zones, edge triggers)
       -> bridge/server.py                (MJPEG + SSE on 127.0.0.1:8765)
       -> onboarding/ (React + TS)        (Monitor 2)
```

Python owns the camera, so the browser never competes for it. Thresholds live in
`tracking/controls.py` alone and are published over `/config`, which is what keeps
the on-screen zones truthful to the input logic.

## Run it

The live product already serves this UI. From the repository root:

```bash
MPLCONFIGDIR=.cache/matplotlib python -m tracking.live --preview
```

That waits until the UI is listening, then opens **http://127.0.0.1:8765/**
(Welcome → practice → live HUD). On macOS that is `/usr/bin/open` on that
URL (`webbrowser.open` often no-ops). If open fails, the log prints the URL
to click. Drag that window to the second monitor. The live HUD camera is a
large **color** MJPEG face feed (not grayscale) with the inner deadzone and
outer follow ring. The native look-axis overlay stays a **separate**
camera/vision window — website chrome is not drawn there. Same MacBook
camera and Quartz holds. Do not start `npm run dev` and do not start a
second camera.

`--no-preview` still serves the same URL (inject + UI server) but does **not**
open a browser, so Luna can keep keyboard focus. Open the URL yourself only
when you are not mid-match.

**Find your center** and the live **Reset center** control (and overlay RESET)
recentre that same live tracker for the whole session. Pose calibration is not
stored in the browser; it lives in the `tracking.live` process and is what
Quartz uses for WASD / Space / L.

UI-only mock, no webcam:

```bash
python -m bridge.server --mock
```

## Bridge endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /config` | thresholds + direction/key mapping + whether video exists |
| `GET /events` | Server-Sent Events stream of the control state |
| `GET /stream.mjpg` | multipart MJPEG of the tracked camera frames |
| `POST /calibrate` | set the current nose and resting mouth as neutral |
| `POST /arm` | start sending real key events to the focused application |
| `POST /disarm` | stop sending key events and release everything held |
| `POST /deadzone-mode` | `{"mode":"fixed"}` or `{"mode":"follow"}` — applies to this process immediately |
| `POST /mock` | drive the mock source (mock mode only) |

Control state matches the contract in `TECHNICAL_SPEC.md`:

```json
{
  "centered": true,
  "nose": {"x": 0.12, "y": -0.08},
  "direction": "NE",
  "keys": ["W", "D"],
  "mouth": {"active": false, "fired": false, "value": 0.03, "confidence": 0.33},
  "wink": {"active": false, "fired": false, "value": 0.01, "confidence": 0.40},
  "eyebrow": {"active": false, "fired": false, "value": 0.10, "confidence": 0.0},
  "tracking": true
}
```

`fired` is true only on the frame a gesture crosses its trigger threshold, so a
held mouth or a closed eye never repeats the action.

## Screens

The phase machine follows `TECHNICAL_SPEC.md`, with `TRANSITION` added for screen 8:

`WELCOME -> EXPLAIN_CONTROLS -> CENTER_CALIBRATION -> MOVEMENT_TRAINING ->
SHOOTING_TRAINING -> PASSING_TRAINING -> COMPLETE -> TRANSITION -> LIVE_TELEMETRY`

Progress persists in `localStorage`, so a refresh does not restart the sequence.

## Demo controls

- `ArrowRight` advances a phase, for stepping through during a presentation.
- `` ` `` toggles the dev panel (connection status, simulated input, restart).

The dev panel can simulate nose position, all eight directions, the mouth and
wink triggers, and tracking lost/found, so the visuals can be worked on with no
webcam present.

## Visual fidelity

Characters are SVG with CSS animation (`src/components/Player.tsx`), which is
tiers 2-3 of the fallback hierarchy in `TECHNICAL_SPEC.md`. They expose the
required poses: idle, run, shoot, pass, receive, celebrate. Swapping in real
low-poly 3D later only touches that one component; no control logic depends on it.

## Match mode

Once training is complete the second monitor becomes the match HUD, and the
output layer turns control state into real key events.

### Semantics

| Gesture | Key | Behaviour |
| --- | --- | --- |
| Head direction | W A S D | held while the direction is active; released at the (fixed or followed) deadzone |
| Mouth open | Space | Space after 200ms open; held while open, so longer open is a more powerful shot |
| Wink | L | single tap; an eye held closed never repeats |

### Before a match

```bash
# 1. confirm macOS will actually deliver synthetic keys
.venv-mediapipe/bin/python -m output.selftest

# 2. start the bridge, which begins DISARMED
MPLCONFIGDIR=.cache/matplotlib .venv-mediapipe/bin/python -m bridge.server
```

If the self-test fails, grant Accessibility permission to the app running the
bridge in System Settings > Privacy & Security > Accessibility and restart it.
Without it macOS discards injected keys silently, which is the usual reason
synthetic input does not reach Luna.

### Running the demo

1. A helper starts the match in Luna on Monitor 1. Head controls cannot navigate
   menus, so hand over at kickoff.
2. Click the game window so it owns the keyboard.
3. On Monitor 2 press **Controls off** to arm. The HUD names the app receiving
   keys, and warns in amber if anything else takes focus.

### Safety

Input is disarmed until asked. Losing tracking, disarming, or stopping the
bridge releases every held key, so a lost face cannot leave the player running.

### Drift

In **fixed** mode, posture settling can walk the player with no input. If the
nose holds still outside the dead zone for 3.5 seconds that is treated as
drift, so neutral is re-set there and the HUD confirms it.

**Follow** skips that timer. A held look (for example D) stays in that
direction; recenter only from eyebrows, overlay RESET, or website Find your
center / Reset center.

### Nose deadzone

The look-axis overlay (`FIFA4ALL look axis`) is the switch used while tracking:
tap **FIXED** or **FOLLOW** under **RESET**. That changes the same
`ControlStateMachine` Quartz reads for WASD.

The live website HUD still has a **Deadzone** switch (persisted in
`localStorage` as `fifa4all.deadzoneMode` and applied with
`POST /deadzone-mode`) if that tab is open.

- **Fixed center** (default): the zone stays on the last calibrate / RESET home.
  Return into that original zone to release WASD.
- **Follow**: two radii. The inner deadzone releases WASD. An outer ring sits
  beyond the WASD chips; the zone only follows when the nose is in that outer
  region (center slides so the nose stays on the ring). Between the rings the
  current direction stays held, so a small move back from the outer edge still
  moves. A held look does not auto-recentre. Recentre only from eyebrows,
  Find your center, Reset center, or overlay RESET. The live HUD camera is a
  large color face feed; the OpenCV look-axis window stays separate.
