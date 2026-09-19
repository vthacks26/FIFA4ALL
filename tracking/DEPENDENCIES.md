# Tracking Dependency Handoff for Person 3

Goal: keep the default application and CI lightweight. The importable tracking geometry, frame objects, and synthetic fixtures currently require only the Python standard library.

## Recommended Dependency Groups

### Core / CI / Simulation

No third-party packages required for:

- `tracking.features`
- `tracking.frames`
- `tracking.synthetic`
- `python -m unittest`

Person 3 can run simulation tests and consume synthetic `MovementFrame` sequences without installing webcam or ML packages.

### Optional Webcam Tracking

Install only on machines that need real webcam tracking. Use Python 3.12; Python 3.14 pulled a different MediaPipe package/API and did not work reliably in local testing.

```text
mediapipe==0.10.14
opencv-python>=4.11,<5
numpy>=1.26,<2
```

Why these are optional:

- `opencv-python` opens the Mac webcam and displays the diagnostic preview.
- `mediapipe` provides the pretrained face landmark tracker.
- `numpy` is pulled in by the diagnostic preview path.

## Performance Notes

- Keep camera processing single-frame and fresh. The tracker sets OpenCV buffer size to `1` and drops stale reads instead of building a queue.
- Use one face only: `max_num_faces=1`.
- Keep `refine_landmarks=True` for mouth stability during early testing; if teammate Macs struggle, first test switching it to `False`.
- Keep preview width capped by `max_width` in `WebcamFaceTracker`; lowering it from `960` to `640` should improve speed.
- Do not add MediaPipe/OpenCV to required app startup paths. Import them only inside webcam modules.
- Do not install these dependencies in CI unless CI has a webcam-specific job.

## Coordination Ask

Person 3 should place these in an optional dependency group, for example `tracking-webcam`, not in the base dependency set. Suggested shape:

```toml
[project.optional-dependencies]
tracking-webcam = [
  "mediapipe==0.10.14; python_version == '3.12'",
  "opencv-python>=4.11,<5",
  "numpy>=1.26,<2",
]
```

If the project does not use `pyproject.toml`, keep them in a separate requirements file such as `requirements-tracking-webcam.txt`.

Verified local setup:

```bash
brew install python@3.12
/opt/homebrew/bin/python3.12 -m venv .venv-mediapipe
.venv-mediapipe/bin/python -m pip install -r tracking/requirements.txt
MPLCONFIGDIR=.cache/matplotlib .venv-mediapipe/bin/python -m tracking.control_preview
```

Observed working labels in the MediaPipe preview: neutral `-`, `W`, `A`, `D`, `D+S`, `A+W`, `Space`, `L`, and combined labels such as `A+W+L` and `D+S+Space`.
