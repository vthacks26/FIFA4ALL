# FIFA4ALL Orientation - Implementation Plan

Source of truth: `vthacks26-onboarding.zip` (README, BRAND_KIT, ORIENTATION_FLOW,
TECHNICAL_SPEC, AGENT_HANDOFF).

## Architecture decisions

- Python keeps the camera, MediaPipe, thresholds and keyboard output.
- Python serves MJPEG video + control-state JSON to the browser over plain HTTP
  (MJPEG multipart + Server-Sent Events). No new Python dependencies.
- Frontend is React + TypeScript + Vite, rendering the nine orientation screens.
- Characters are SVG/CSS (spec MVP fallback tiers 2-3), not 3D.
- Thresholds live in one Python module and are published to the UI, so the
  visualization is truthful per TECHNICAL_SPEC.

## Phase 1 - Shared control state (Python)

- [ ] `tracking/controls.py`: thresholds, 9-zone direction classifier with
      hysteresis, edge-triggered mouth/wink latches, calibrated center
- [ ] Emit the UI state contract from TECHNICAL_SPEC verbatim
- [ ] Unit tests: dead zone, diagonals, hysteresis/no-chatter, edge triggers,
      tracking-loss releases keys

## Phase 2 - Bridge server (Python)

- [ ] `bridge/server.py`: `/stream.mjpg`, `/events` (SSE), `POST /calibrate`,
      `GET /config` (thresholds)
- [ ] `--mock` mode so the UI runs with no webcam
- [ ] Unit tests for the state/serialization boundary

## Phase 3 - Frontend foundation

- [ ] Vite + React + TS scaffold under `onboarding/`
- [ ] Brand tokens (color, type, motion) from BRAND_KIT
- [ ] `useControlState` hook: live SSE source or mock source
- [ ] Dev panel simulating nose, direction, mouth, wink, tracking lost/found
- [ ] Orientation state machine with progress persisted across refresh

## Phase 4 - Screens

- [ ] 1 Welcome
- [ ] 2 Controls overview
- [ ] 3 Find your center (dwell -> lock)
- [ ] 4 Drill 01 Movement (N/S/E/W validation)
- [ ] 5 Drill 02 Shooting (3 activations)
- [ ] 6 Drill 03 Passing (3 activations)
- [ ] 7 Training complete (player card)
- [ ] 8 Transition to game (ball wipe)
- [ ] 9 Live match telemetry

## Phase 5 - Motion + polish

- [ ] Ball wipe transitions, pitch draw, tracking lock, goal burst, pass trail
- [ ] Nose-ball reticle as the signature motif, reused in live telemetry

## Verification

- [ ] `python -m unittest` green
- [ ] `tsc --noEmit` clean, no `any`
- [ ] Full flow completes in mock mode
- [ ] Full flow completes against live webcam
