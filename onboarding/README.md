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
| `POST /calibrate` | set the current nose position as neutral |
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
