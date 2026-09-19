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

- [x] `tracking/controls.py`: thresholds, 9-zone direction classifier with
      hysteresis, edge-triggered mouth/wink latches, calibrated center
- [x] Emit the UI state contract from TECHNICAL_SPEC verbatim
- [x] Unit tests: dead zone, diagonals, hysteresis/no-chatter, edge triggers,
      tracking-loss releases keys

## Phase 2 - Bridge server (Python)

- [x] `bridge/server.py`: `/stream.mjpg`, `/events` (SSE), `POST /calibrate`,
      `GET /config` (thresholds)
- [x] `--mock` mode so the UI runs with no webcam
- [x] Unit tests for the state/serialization boundary

## Phase 3 - Frontend foundation

- [x] Vite + React + TS scaffold under `onboarding/`
- [x] Brand tokens (color, type, motion) from BRAND_KIT
- [x] `useControlState` hook: live SSE source or mock source
- [x] Dev panel simulating nose, direction, mouth, wink, tracking lost/found
- [x] Orientation state machine with progress persisted across refresh

## Phase 4 - Screens

- [x] 1 Welcome
- [x] 2 Controls overview
- [x] 3 Find your center (dwell -> lock)
- [x] 4 Drill 01 Movement (N/S/E/W validation)
- [x] 5 Drill 02 Shooting (3 activations)
- [x] 6 Drill 03 Passing (3 activations)
- [x] 7 Training complete (player card)
- [x] 8 Transition to game (ball wipe)
- [x] 9 Live match telemetry

## Phase 5 - Motion + polish

- [x] Ball wipe transitions, pitch draw, tracking lock, goal burst, pass trail
- [x] Nose-ball reticle as the signature motif, reused in live telemetry

## Verification

- [x] `python -m unittest` green
- [x] `tsc --noEmit` clean, no `any`
- [x] Full flow completes in mock mode
- [x] Full flow completes against live webcam

## Status

All phases complete and verified on 2026-09-19.

Verified:
- `python -m unittest` - 47 tests pass
- `tsc --noEmit` clean, `eslint --max-warnings 0` clean, no `any` in the codebase
- full flow walked in mock mode through all nine screens
- real webcam mode confirmed: MediaPipe on Metal, `has_video: true`,
  50 JPEG frames captured in 5s, MJPEG rendering in the browser at 640x360,
  tracking-loss states showing correctly

Fixed during verification:
- calibration locked but never advanced (effect cleanup cancelled its own timer)
- goal overlapped the shooter on the shooting drill
- pass trajectory stopped short of the teammate
- lime "4" was invisible on the gold player card
- bridge logged a traceback on every browser disconnect
- webcam overlay was hard to read on a bright feed

Not built, per "do not overbuild" in AGENT_HANDOFF.md:
adaptive-disability presets, AI control discovery, accounts, settings dashboards,
analytics, extra FIFA commands.

Deferred: real low-poly 3D characters. Isolated to `src/components/Player.tsx`.
