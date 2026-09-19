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
- [ ] Single `read()` in `_read_fresh_frame` (measured 100ms -> 33ms per frame)
- [ ] Regression test pinning the single-read behaviour
- [ ] Angular hysteresis on zone boundaries so NE/N does not chatter

### Phase B - keyboard output layer
- [ ] `output/keyboard.py`: Quartz CGEvent backend + recording backend for tests
- [ ] `output/session.py`: diff control state into key down/up events
- [ ] Hold semantics for W/A/S/D and Space, tap semantics for L
- [ ] Arm / disarm / release-all
- [ ] Tests covering hold, release, tap, tracking loss, disarm

### Phase C - in-game safety
- [ ] Frontmost-application watchdog published to the UI
- [ ] Re-centre with no keyboard
- [ ] Accessibility permission detection with a clear message

### Phase D - match-mode UI
- [ ] Armed / disarmed state on the live screen
- [ ] Focus warning when the game is not frontmost
- [ ] Shot power meter driven by mouth-open duration
- [ ] Recent-action feed so spectators see cause and effect

### Phase E - end to end
- [ ] Prove injected keys reach a real browser (same chain Luna uses)
- [ ] Document the Accessibility permission steps

## Verification
- [ ] `python -m unittest` green
- [ ] `tsc --noEmit` and eslint clean, no `any`
- [ ] Measured frame time at or under 40ms
- [ ] Keys observed arriving in a browser text field
