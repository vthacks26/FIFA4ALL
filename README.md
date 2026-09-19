# FIFA4ALL

> **Different bodies. Same pitch.**

Play EA Sports FC using body movements instead of a controller. A webcam detects
head movement and facial gestures and converts them into keyboard input:

```
Head movement  -> WASD
Mouth "O"      -> Space
```

See [`joe_plan.txt`](joe_plan.txt) for the full product vision and milestones.

## Architecture

```
webcam -> vision (landmarks / head pose) -> controls (intent) -> output (keyboard) -> Amazon Luna -> EA FC
```

The layers are decoupled so the control and output logic can be developed and
unit-tested headlessly, without a camera or display.

```
fifa4all/
  vision/    face_landmarks.py   # MediaPipe FaceLandmarker wrapper
             head_pose.py        # yaw/pitch/roll + smoothing
  controls/  head_direction.py   # dead zones + diagonals -> WASD
             mouth_action.py     # mouth-O activation cycle -> Space
  output/    keyboard.py         # keyboard abstraction (logging / pynput backends)
  pipeline.py                    # ties the layers together
  app.py                         # demo runner
tests/                           # pytest suite (pure-logic + vision smoke test)
```

## Development setup

Requires Python 3.10+ (tested on 3.12). The setup script installs the system
libraries MediaPipe needs, creates a virtualenv, installs dependencies and
downloads the face model:

```bash
bash scripts/setup.sh
source .venv/bin/activate
```

On the Mac that actually plays the game, also install the real keyboard backend:

```bash
pip install -r requirements-macos.txt
```

## Running the demo

The synthetic demo drives the full control + keyboard pipeline with no camera,
model or display — great for CI and cloud environments:

```bash
python -m fifa4all.app --synthetic
```

Run the real vision stack on a still image:

```bash
python -m fifa4all.app --image path/to/face.jpg
```

Live webcam mode (local Mac, needs a camera and — for real key injection — the
`pynput` backend):

```bash
python -m fifa4all.app --webcam
```

## Tests

```bash
pytest
```

The pure-logic tests always run. The vision smoke test runs only when the
MediaPipe model bundle has been downloaded.
