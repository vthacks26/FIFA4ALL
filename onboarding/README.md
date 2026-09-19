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

Two processes. From the repository root:

```bash
# 1. tracking bridge (real webcam)
MPLCONFIGDIR=.cache/matplotlib .venv-mediapipe/bin/python -m bridge.server

# 1b. or with no webcam at all
.venv-mediapipe/bin/python -m bridge.server --mock

# 2. orientation UI
cd onboarding && npm install && npm run dev
```

Open http://localhost:5173 on the second monitor. If the bridge is not running
the UI falls back to simulated input automatically.

## Bridge endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /config` | thresholds + direction/key mapping + whether video exists |
| `GET /events` | Server-Sent Events stream of the control state |
| `GET /stream.mjpg` | multipart MJPEG of the tracked camera frames |
| `POST /calibrate` | set the current nose and resting mouth as neutral |
| `POST /arm` | start sending real key events to the focused application |
| `POST /disarm` | stop sending key events and release everything held |
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
| Head direction | W A S D | held while the direction is active, released at centre |
| Mouth open | Space | held while open, so longer open is a more powerful shot |
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

Posture settles over a few minutes and the neutral centre moves with it, which
makes the player walk with no input. If the nose holds still outside the dead
zone for 3.5 seconds that is drift rather than intent, so neutral is re-set
there and the HUD confirms it. The window is deliberately longer than a steering
input is ever held perfectly still.
