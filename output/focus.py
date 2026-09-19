"""Which application currently owns the keyboard.

Injected key events go to the frontmost application, so if anyone clicks the
telemetry UI on the second monitor the game silently stops responding. The
second monitor has to show this, otherwise the failure looks like broken
tracking and nobody can diagnose it mid-demo.

Frontmost app is read through `osascript`, following `tracking/live.py` on
cursor/tracking-quartz-live-a2a3. A pyobjc version of this module threw
`KeyError` on some builds, because pyobjc's lazy importer does not raise
`ImportError` for a missing symbol, which took the whole state stream down.
Shelling out has no such dependency and cannot fail that way.
"""

from __future__ import annotations

import subprocess
import sys

# Applications that can plausibly be hosting the Amazon Luna session.
BROWSER_NAMES = frozenset(
    {
        "Google Chrome",
        "Google Chrome Canary",
        "Chromium",
        "Safari",
        "Safari Technology Preview",
        "Firefox",
        "Microsoft Edge",
        "Arc",
        "Brave Browser",
    }
)

_FRONTMOST_SCRIPT = (
    'tell application "System Events" to get name of first '
    "application process whose frontmost is true"
)


def frontmost_application() -> str | None:
    """Name of the frontmost app, or None when it cannot be determined."""

    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            ["osascript", "-e", _FRONTMOST_SCRIPT],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    name = result.stdout.strip()
    return name or None


def game_has_focus(frontmost: str | None) -> bool:
    """True when a browser is frontmost and could be receiving the keys."""

    return frontmost is not None and frontmost in BROWSER_NAMES


def restore_game_focus(app: str = "Google Chrome") -> bool:
    """Hand key focus back to the browser without the user clicking.

    Taken from `tracking/overlay.py`. Used after the overlay window is created,
    since creating a window can take focus even when it is non-activating.
    """

    if sys.platform != "darwin":
        return False
    try:
        subprocess.run(
            ["osascript", "-e", f'tell application "{app}" to activate'],
            capture_output=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return True
