"""Always-on-top, non-activating macOS overlay for the live camera preview.

OpenCV's HighGUI window would otherwise become key and steal Luna/Chrome
focus. After the first ``imshow``, we retarget that Cocoa window: floating
level and ``NSWindowStyleMaskNonactivatingPanel``. Mouse events stay enabled
so the on-canvas Reset button can be tapped.
"""

from __future__ import annotations

import sys
from typing import Any

WINDOW_TITLE = "FIFA4ALL look axis"

# NSWindowStyleMaskNonactivatingPanel
_NONACTIVATING_PANEL = 1 << 7
# NSWindowCollectionBehaviorCanJoinAllSpaces | FullScreenAuxiliary | Stationary
_COLLECTION = (1 << 0) | (1 << 8) | (1 << 4)
# NSStatusWindowLevel — sits above a fullscreen Chrome/Luna space
_FLOATING_LEVEL = 25


def decorate_overlay_window(title: str = WINDOW_TITLE) -> bool:
    """Make the OpenCV window float without becoming key. False if unavailable."""

    if sys.platform != "darwin":
        return False
    try:
        import ctypes
        from ctypes import c_bool, c_char_p, c_long, c_ulong, c_void_p
    except ImportError:
        return False

    objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
    objc.objc_getClass.restype = c_void_p
    objc.objc_getClass.argtypes = [c_char_p]
    objc.sel_registerName.restype = c_void_p
    objc.sel_registerName.argtypes = [c_char_p]
    ctypes.CDLL(
        "/System/Library/Frameworks/AppKit.framework/AppKit",
        mode=ctypes.RTLD_GLOBAL,
    )

    def _sel(name: str) -> c_void_p:
        return objc.sel_registerName(name.encode("utf-8"))

    def _send(obj: Any, selector: str, *args: Any, restype=c_void_p, argtypes=None):
        func = objc.objc_msgSend
        func.restype = restype
        extra = argtypes if argtypes is not None else [c_void_p] * len(args)
        func.argtypes = [c_void_p, c_void_p, *extra]
        return func(obj, _sel(selector), *args)

    app = _send(objc.objc_getClass(b"NSApplication"), "sharedApplication")
    if not app:
        return False
    windows = _send(app, "windows")
    if not windows:
        return False
    count = int(_send(windows, "count", restype=c_ulong, argtypes=[]) or 0)
    found = False
    for index in range(count):
        window = _send(
            windows,
            "objectAtIndex:",
            index,
            restype=c_void_p,
            argtypes=[c_ulong],
        )
        if not window:
            continue
        ns_title = _send(window, "title")
        raw = (
            _send(ns_title, "UTF8String", restype=c_char_p, argtypes=[])
            if ns_title
            else None
        )
        name = raw.decode("utf-8") if raw else ""
        if title not in name and name not in title:
            continue
        mask = int(_send(window, "styleMask", restype=c_ulong, argtypes=[]) or 0)
        _send(
            window,
            "setStyleMask:",
            mask | _NONACTIVATING_PANEL,
            restype=None,
            argtypes=[c_ulong],
        )
        _send(window, "setLevel:", _FLOATING_LEVEL, restype=None, argtypes=[c_long])
        _send(
            window,
            "setHidesOnDeactivate:",
            False,
            restype=None,
            argtypes=[c_bool],
        )
        _send(
            window,
            "setCollectionBehavior:",
            _COLLECTION,
            restype=None,
            argtypes=[c_ulong],
        )
        _send(
            window,
            "setIgnoresMouseEvents:",
            False,
            restype=None,
            argtypes=[c_bool],
        )
        _send(window, "orderFrontRegardless", restype=None, argtypes=[])
        found = True
    return found


def restore_chrome_focus() -> None:
    """If the overlay stole key focus, give it back to Chrome without clicking."""

    if sys.platform != "darwin":
        return
    import subprocess

    try:
        subprocess.run(
            ["osascript", "-e", 'tell application "Google Chrome" to activate'],
            check=False,
            timeout=2,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError):
        return
