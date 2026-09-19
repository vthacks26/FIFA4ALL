"""FIFA4ALL: play EA Sports FC with head movement and facial gestures.

Architecture (see joe_plan.txt):

    webcam -> vision (landmarks) -> controls (intent) -> output (keyboard)

The layers are deliberately decoupled so the control and output logic can be
developed and unit-tested headlessly, without a camera or a display.
"""

__version__ = "0.1.0"
