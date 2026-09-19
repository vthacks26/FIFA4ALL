# FIFA4ALL Custom Controls - Implementation Plan

Builds on the orientation flow in `ONBOARDING_PLAN.md`, which is complete.

Goal: during orientation the player picks an action, performs whatever movement
they can, and the system binds that action to the movement they actually made.

## Design decision

Adaptive rebinding is **silent**. When a drill asks for one gesture and the
player reliably performs a different one, the binding switches to what they did.
Repeating the movement is what confirms it; there is no separate confirm step.

Rationale: confirming a switch needs an input, and during orientation the player
may not have one bound yet. Silence avoids that chicken-and-egg. The switch is
shown plainly on screen and the drill can be repeated to change it.

## Channel eligibility rule

Every candidate gesture must ship with all three of these before it is offered.
This is the existing wink treatment generalized, not a new standard.

1. A per-user resting value sampled at calibration, not a constant
   (see `mouth_rest_clearance`, `eye_open_floor`).
2. A hysteresis pair, trigger high and release low (`wink_on` / `wink_off`).
3. A documented gate against its involuntary confound, measured on a real face
   (see `eye_open_fraction`, which separates wink from blink).

Excluded outright: any gesture whose involuntary rate is non-trivial and which
has no duration or companion-signal gate. Blink is excluded permanently. A
gesture is also rejected if it fires during the rest test in Phase 4.

## Phase 1 - Bindings become data

- [ ] `tracking/bindings.py`: `Action` (MOVE_N/E/S/W, SHOOT, PASS) and
      `GestureChannel` (named scalar + direction + required landmarks)
- [ ] Binding map `Action -> GestureChannel`, with today's mapping as default
- [ ] `DIRECTION_KEYS` and the mouth/wink constants read from the map
- [ ] Publish the active map over `GET /config` alongside thresholds
- [ ] Tests: default map reproduces current behaviour exactly

## Phase 2 - Generic drill screen

- [ ] Parameterize `DrillShooting`/`DrillPassing` over `{action, channel}`
      instead of `state.mouth` / `state.wink`
- [ ] Action picker screen listing available actions and candidate gestures
- [ ] Tests: drill completes against any channel, mock mode

## Phase 3 - Channel vocabulary

Each channel below is a separate task and must satisfy the eligibility rule.

- [x] `brow_raise` - brow-to-eye distance, normalized by face width.
      Gated on `head_pitch`: nodding is the N/S steering axis, and pitch moves
      the brow gap by several percent of itself.
- [x] `cheek_puff` - registered **not selectable**. The bulge is out of plane,
      so the 2D landmarks see one or two percent, less than head yaw moves the
      same measurement. No gate can separate them; revisit with blendshapes.
- [x] `smile_width` - mouth corner separation. Gated on `mouth_opening` near
      rest, which rejects the yawn and stops it co-firing with `mouth_open`.
- [x] `jaw_lateral` - jaw slide left/right, measured chin-against-nose and
      projected onto the eye line so head roll cancels. Gated on `head_turn`
      for the yaw residual.
- [x] `mouth_pucker` - registered **not selectable**. It is lip gap over
      corner separation, so a jaw drop raises it harder than a pucker does and
      it would fire on every shot. Protrusion is not visible in 2D.
- [ ] Per-channel rest calibration folded into the existing calibrate step
      (needs `tracking/controls.py`, which also owns the new gate names
      `head_level`, `mouth_near_rest` and `facing_forward`)
- [x] Tests per channel: rest baseline, trigger, release, confound gate

## Phase 4 - Adaptive rebind

- [ ] Run all eligible channels during a drill, not just the asked one
- [ ] Pulse detector: crosses trigger, holds min duration, returns below release
- [ ] Specificity scoring - a challenger wins only if it is the dominant channel
      by a margin AND the asked channel stayed near its resting value.
      Guards against side effects: a jaw drop perturbs every face-width
      normalized measure, so raw magnitude alone will pick the wrong channel.
- [ ] Distinguish three outcomes, do not collapse them:
      no signal -> suggest another gesture;
      asked channel but weak -> lower this user's threshold, keep binding;
      different channel repeated -> rebind
- [ ] Switching resets the repetition count; the new gesture earns its own reps
- [ ] Show the switch on screen in plain language
- [ ] Rest test: after confirming, watch 15s of rest and reject the channel if
      it fires. Three reps prove the player can perform it; only rest proves it
      will not fire by accident during a match.
- [ ] Conflict check: reject a binding whose channel co-fires with one already
      bound
- [ ] Tests: each outcome, side-effect rejection, rest-test rejection

## Phase 5 - Profile persistence

- [ ] `profiles/<name>.json`: bindings, per-user thresholds, rest baselines
      (`profiles/` is already gitignored)
- [ ] Versioned schema, load on start, rerun orientation to change
- [ ] Tests: round trip, forward-compatible load

## Verification

- [ ] `python -m unittest` green
- [ ] `tsc --noEmit` clean, `eslint --max-warnings 0`, no `any`
- [ ] Full flow in mock mode with a rebind forced from the dev panel
- [ ] Two profiles with different bindings both play
- [ ] Live webcam run

## Notes

- Phases 1, 2, 4 and 5 are testable in mock mode with no camera, using the
  existing dev panel. Only Phase 3 needs a real face.
- Camera access is currently blocked by macOS TCC for the VS Code host.
