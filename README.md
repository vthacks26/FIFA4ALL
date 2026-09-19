# FIFA4ALL

**Different bodies. Same pitch.**

Face-controlled keyboard input for **EA Sports FC** streamed through **Amazon Luna in Google Chrome** on a Mac (US keyboard).

This branch is an independent MVP. It does not reuse `feature/tracking` or PR #1.

## Locked MVP mappings

| Gesture | OS key | Behavior |
| --- | --- | --- |
| Head / face left | `A` | Held while tilted left |
| Head / face right | `D` | Held while tilted right |
| Head / face up | `W` | Held while tilted up |
| Head / face down | `S` | Held while tilted down |
| Diagonals (e.g. up-right) | `W+D` | Simultaneous holds |
| Mouth open | `Space` | **Held while open** (shot strength) |
| Wink (one eye closed) | `L` | **Held while winking** (pass strength) |
| Blink (both eyes) | — | Does **not** press `L` |
| Neutral / face lost | — | All keys released |

Customizable gestures are **not** in this MVP.

Verified **manual** Luna keys (human typing): WASD = movement, Space = shoot, L = pass.  
**Luna-on-Mac with synthetic OS keys is not verified** from this Linux cloud environment.

## How to run on a Mac

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Grant macOS Accessibility (and Input Monitoring if prompted). Exact clicks: [MACOS.md](MACOS.md).

Then:

```bash
# 1. Focus check — no camera. Click Chrome/Luna during the countdown.
python -m fifa4all --key-smoke

# 2. Headless mapping check (safe on any OS)
python -m fifa4all --replay tests/fixtures/replay_mixed.json --print-events

# 3. Live face control
# Calibrate with a still, closed-mouth face. Then click the Chrome Luna window.
python -m fifa4all --no-preview
```

Use `--no-preview` while playing so the OpenCV window does not steal focus from Chrome. Preview is useful for setup:

```bash
python -m fifa4all
```

Press `q` or `Esc` to quit. Quit always releases held keys.

## Architecture

```text
webcam
  → MediaPipe Face Mesh landmarks
  → yaw / pitch / mouth / eye-aspect features
  → hold-intent (WASD, Space, L)
  → OS key down/up (Quartz CGEvent on macOS)
  → focused Google Chrome → Amazon Luna → EA FC
```

Browser `KeyboardEvent` injection is intentionally not used.

## Tests (headless, no camera, no Luna)

```bash
pip install -r requirements-dev.txt
python -m pytest tests/
```

## Docs

- [MACOS.md](MACOS.md) — Accessibility + Chrome-foreground steps
- [SPEC.md](SPEC.md) — mappings, non-goals, injector
- [DEMO.md](DEMO.md) — intended live demo (unverified on Luna)
- [STATUS.md](STATUS.md) — working / unverified
- [EVALS.md](EVALS.md) — automated checks vs remaining Mac checks
