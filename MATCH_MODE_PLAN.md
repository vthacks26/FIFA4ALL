# FIFA4ALL Match Mode - in-game plan

Onboarding is done. This covers what happens once the user is actually playing
EA Sports FC on Monitor 1.

## The gap

The pipeline currently ends at control state. Nothing presses keys. Everything
below exists to close that, safely.

## In-game UX analysis

### Focus is the silent failure
Injected keys go to the frontmost application. If anyone clicks the telemetry UI
on Monitor 2, input stops reaching Luna with no visible cause. The second monitor
must show which app currently owns the keyboard.

### Hold vs tap
- Movement is continuous: W/A/S/D are held while a direction is active and
  released on return to centre.
- Shooting is analogue: mouth-open holds Space, so longer open = more powerful
  shot. Decided over a fixed tap.
- Passing is discrete: a wink taps L once. An eye held closed must not repeat.

### Safety
Tracking loss, disarm, and process exit must all release every held key.
Otherwise a lost face leaves the player sprinting into a corner. Arming is
explicit so the system never types into a form or a menu by accident.

### Drift
Posture settles over a few minutes, the calibrated centre moves, and the player
walks constantly. Re-centring must not need a keyboard.

### Menus
WASD/Space/L cannot navigate Luna or the FC menus. A helper starts the match and
hands over at kickoff. Out of scope for the MVP.

## To do

### Phase A - latency and stability
- [x] Single `read()` in `_read_fresh_frame` (measured 100ms -> 33ms per frame)
- [x] Regression test pinning the single-read behaviour
- [x] Angular hysteresis on zone boundaries so NE/N does not chatter

### Phase B - keyboard output layer
- [x] `output/keyboard.py`: Quartz CGEvent backend + recording backend for tests
- [x] `output/session.py`: diff control state into key down/up events
- [x] Hold semantics for W/A/S/D and Space, tap semantics for L
- [x] Arm / disarm / release-all
- [x] Tests covering hold, release, tap, tracking loss, disarm

### Phase C - in-game safety
- [x] Frontmost-application watchdog published to the UI
- [x] Re-centre with no keyboard
- [x] Accessibility permission detection with a clear message

### Phase D - match-mode UI
- [x] Armed / disarmed state on the live screen
- [x] Focus warning when the game is not frontmost
- [x] Shot power meter driven by mouth-open duration
- [x] Recent-action feed so spectators see cause and effect

### Phase E - end to end
- [x] Prove injected keys reach a real browser (same chain Luna uses)
- [x] Document the Accessibility permission steps

## Verification
- [x] `python -m unittest` green
- [x] `tsc --noEmit` and eslint clean, no `any`
- [x] Measured frame time at or under 40ms
- [x] Keys observed arriving in a browser text field

## Status

Built and verified on 2026-09-19. 102 Python tests pass; frontend typecheck,
lint and build are clean with no `any`.

### Measured

| Thing | Before | After |
| --- | --- | --- |
| Tracking frame time | 100 ms (10 fps) | 34 ms (30 fps) |
| Keyboard output | did not exist | Quartz CGEvent at the HID tap |

### Bugs this surfaced, with evidence

- **Shoot latch stuck open.** A tester's resting mouth measured 0.064, above the
  0.060 release threshold, so once Space was pressed it never released.
  Calibration now samples resting mouth and lifts the release clear of it.
- **Shot power always read 0.** Duration was tracked in the output layer, which
  only runs when armed, so the UI showed "CHARGING 0.0s" forever. Duration moved
  into the state machine.
- **Startup warnings were invisible.** Block buffering swallowed the banner when
  logs were piped, hiding the permission warning before a demo.
- **Permission check gave a false negative.** Creating an event tap succeeds on a
  process that is still barred from posting, so the check reported "ready" for a
  setup where nothing worked. Replaced with a post-and-observe round trip.

## Blocked on you: Accessibility permission

`output.selftest` currently fails:

```text
FAIL: macOS is discarding synthetic key events
```

This is the same blocker recorded in `joe_plan.txt` as "synthetic keyboard events
not reaching Luna", and it is a permission only you can grant:

1. System Settings > Privacy & Security > Accessibility
2. Add the app that runs the bridge (Terminal, iTerm or your IDE), enable it
3. Restart that app completely
4. Verify: `.venv-mediapipe/bin/python -m output.selftest` should print `PASS`

Until then `/arm` refuses with that message rather than pretending to work.

## Still open

- Real low-poly 3D characters, still isolated to `src/components/Player.tsx`.
- Menu navigation. WASD/Space/L cannot drive Luna or FC menus, so a helper starts
  the match and hands over at kickoff.
- `mouth_open` at 0.090 was tuned by the team on their own faces. Now that
  calibration adapts per face, re-check it with each player before the demo.
