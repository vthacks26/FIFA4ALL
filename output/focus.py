"""Which application currently owns the keyboard.

Injected key events go to the frontmost application, so if anyone clicks the
telemetry UI on the second monitor the game silently stops responding. The
second monitor has to show this, otherwise the failure looks like broken
tracking and nobody can diagnose it mid-demo.
"""

from __future__ import annotations

from typing import Any

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


def frontmost_application() -> str | None:
    """Name of the frontmost app, or None when it cannot be determined."""

    try:
        from Quartz import (  # type: ignore[import-not-found]
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListExcludeDesktopElements,
            kCGWindowListOptionOnScreenOnly,
        )
    except ImportError:
        return None

    options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
    windows: Any = CGWindowListCopyWindowInfo(options, kCGNullWindowID)
    if not windows:
        return None

    for window in windows:
        # Layer 0 is the normal application layer; menu bars and overlays sit
        # above it and would otherwise be reported as frontmost.
        if window.get("kCGWindowLayer") != 0:
            continue
        name = window.get("kCGWindowOwnerName")
        if name:
            return str(name)
    return None


def game_has_focus(frontmost: str | None) -> bool:
    """True when a browser is frontmost and could be receiving the keys."""

    return frontmost is not None and frontmost in BROWSER_NAMES
