# STATUS

```text
WORKING
- Landmark feature extraction (yaw/pitch/MAR/EAR) with tests
- Hold-while-active WASD / Space / L intent (dead zone, hysteresis, diagonals)
- Blink is not treated as a wink
- Face-lost and process-exit release all keys
- Quartz CGEvent injector module (macOS-only; raises on Linux)
- Recording / dry-run injectors and JSON replay
- Headless pytest suite on Linux
- Overlay HUD for preview mode

UNVERIFIED / NOT RUN HERE
- macOS Accessibility grant
- Quartz events reaching Google Chrome
- Amazon Luna accepting synthetic HID keys
- EA FC shot/pass strength from held Space/L
- Live webcam + MediaPipe on a Mac
- End-to-end latency

CURRENT TASK
- Independent face-control MVP (not based on feature/tracking or PR #1)

NEXT
- On a Mac: Accessibility → --key-smoke into a text field → --key-smoke into Luna
- Then live camera with --no-preview

DO NOT TOUCH
- Do not merge or copy feature/tracking or PR #1 into this branch
- Do not add customizable-gesture UI in this MVP
```
