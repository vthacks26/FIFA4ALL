# FIFA4ALL face-control MVP spec

## Target

- Game: EA Sports FC
- Stream: Amazon Luna
- Browser: Google Chrome
- Host: Mac, default US keyboard
- Output: real OS key down/up (Quartz `CGEvent` on macOS), not DOM `KeyboardEvent`s

## Locked mappings (this PR)

| Intent | Key | Hold policy |
| --- | --- | --- |
| Move forward | W | Hold while head/face is up |
| Move left | A | Hold while head/face is left |
| Move back | S | Hold while head/face is down |
| Move right | D | Hold while head/face is right |
| Shoot | Space | Hold while mouth is open (strength) |
| Pass | L | Hold while winking (strength) |

Diagonals are allowed (`W+A`, `W+D`, `S+A`, `S+D`). Face lost or process exit releases every key.

## Non-goals

- Customizable / trained gestures
- Training Camp / adaptive mapping
- Virtual gamepad / Xbox emulation
- Voice, eye-gaze-only control, or full camera look
- Claiming Luna-on-Mac verification from Linux CI

## Pipeline

1. Camera (optional mirror so looking left = left)
2. MediaPipe Face Mesh landmarks
3. Features: yaw, pitch, mouth aspect ratio, left/right eye aspect ratio
4. Gesture engine: EMA, dead zone, hysteresis, hold-while-active
5. `HeldKeySession` diffs desired vs current keys
6. Injector: Quartz HID (Mac), pynput fallback, recording/dry-run for tests

## Headless / simulation path

`python -m fifa4all --replay tests/fixtures/replay_mixed.json --print-events`

Replay JSON is a list of feature frames (`yaw`, `pitch`, `mouth_open`, `left_ear`, `right_ear`, optional `detected`). No webcam and no macOS APIs are required.

`--key-smoke` posts a canned WASD / Space / L hold sequence for Mac injector bring-up.

## Environment limits

Development and pytest ran on a Linux cloud VM without Accessibility, Chrome, Luna, or EA FC. Live Mac + Luna remains a manual checklist in [MACOS.md](MACOS.md) and [EVALS.md](EVALS.md).
