"""macOS Accessibility / Input Monitoring checks."""

from __future__ import annotations

import sys


MACOS_PERMISSION_HELP = """
macOS must authorize this process to post HID keyboard events.

1. Open System Settings → Privacy & Security → Accessibility
2. Click the lock / use Touch ID if needed
3. Enable the terminal app you will use to launch FIFA4ALL
   (Terminal, iTerm, Prompt, or the Python binary if it appears)
4. Also check System Settings → Privacy & Security → Input Monitoring
   and enable the same app if macOS lists it
5. Quit FIFA4ALL fully and start it again after toggling permission
6. Click Google Chrome so it is the frontmost app — OS keys go to the
   focused application, not to a background Luna tab

This Linux cloud environment cannot grant those permissions or focus Chrome.
""".strip()


def is_macos() -> bool:
    return sys.platform == "darwin"


def accessibility_trusted() -> bool | None:
    """True/False on macOS; None on other platforms."""
    if not is_macos():
        return None
    try:
        import ctypes
        import ctypes.util

        path = ctypes.util.find_library("ApplicationServices") or (
            "/System/Library/Frameworks/ApplicationServices.framework/"
            "ApplicationServices"
        )
        lib = ctypes.cdll.LoadLibrary(path)
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        lib.AXIsProcessTrusted.argtypes = []
        return bool(lib.AXIsProcessTrusted())
    except OSError:
        return False


def prompt_accessibility() -> bool | None:
    """Ask macOS to show the Accessibility prompt. None if not Darwin."""
    if not is_macos():
        return None
    try:
        import ctypes
        import ctypes.util

        path = ctypes.util.find_library("ApplicationServices") or (
            "/System/Library/Frameworks/ApplicationServices.framework/"
            "ApplicationServices"
        )
        lib = ctypes.cdll.LoadLibrary(path)
        # AXIsProcessTrustedWithOptions may fail if we cannot build a CF dict;
        # the boolean check is still useful.
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        lib.AXIsProcessTrusted.argtypes = []
        return bool(lib.AXIsProcessTrusted())
    except OSError:
        return False
