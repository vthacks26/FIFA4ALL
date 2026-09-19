"""Always-on-top, non-activating macOS overlay for the live camera preview.

OpenCV's HighGUI window would otherwise become key and steal Luna/Chrome
focus. After the first ``imshow``, we retarget that Cocoa window: floating
level and ``NSWindowStyleMaskNonactivatingPanel``. The window accepts mouse
events and hosts a real AppKit Reset button (not click-through).
"""

from __future__ import annotations

import re
import sys
from ctypes import Structure, c_double
from typing import Any

WINDOW_TITLE = "FIFA4ALL look axis"
RESET_CONTROL_TITLE = "Reset"

# NSWindowStyleMaskNonactivatingPanel
_NONACTIVATING_PANEL = 1 << 7
# NSWindowCollectionBehaviorCanJoinAllSpaces | FullScreenAuxiliary | Stationary
_COLLECTION = (1 << 0) | (1 << 8) | (1 << 4)
# NSStatusWindowLevel — sits above a fullscreen Chrome/Luna space
_FLOATING_LEVEL = 25
# NSWindowAbove
_WINDOW_ABOVE = 1
# NSButtonTypeOnOff — poll state instead of an ObjC action IMP
_BUTTON_ON_OFF = 6
_BEZEL_ROUNDED = 1
_NS_ON = 1

_RESET_PANEL: Any = None
_RESET_BUTTON: Any = None


class _NSPoint(Structure):
    _fields_ = [("x", c_double), ("y", c_double)]


class _NSSize(Structure):
    _fields_ = [("width", c_double), ("height", c_double)]


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
        _attach_reset_button(window, _send, _sel, objc)
        found = True
    return found


def poll_reset_click() -> bool:
    """True once when the AppKit Reset button is toggled on (a real click)."""

    button = _RESET_BUTTON
    if not button or sys.platform != "darwin":
        return False
    try:
        import ctypes
        from ctypes import c_long, c_void_p
    except ImportError:
        return False
    objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
    objc.sel_registerName.restype = c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    func = objc.objc_msgSend
    func.restype = c_long
    func.argtypes = [c_void_p, c_void_p]
    state = int(func(button, objc.sel_registerName(b"state")) or 0)
    if state != _NS_ON:
        return False
    func.restype = None
    func.argtypes = [c_void_p, c_void_p, c_long]
    func(button, objc.sel_registerName(b"setState:"), 0)
    return True


def parse_ns_frame(description: str) -> tuple[float, float, float, float] | None:
    nums = re.findall(r"[-0-9.]+", description)
    if len(nums) < 4:
        return None
    return float(nums[0]), float(nums[1]), float(nums[2]), float(nums[3])


def _attach_reset_button(window: Any, _send: Any, _sel: Any, objc: Any) -> None:
    """Child panel with a real NSButton. Receives clicks; parent is not click-through."""

    global _RESET_PANEL, _RESET_BUTTON
    from ctypes import c_bool, c_char_p, c_long, c_ulong, c_void_p

    def _nsstring(text: str) -> Any:
        return _send(
            objc.objc_getClass(b"NSString"),
            "stringWithUTF8String:",
            text.encode("utf-8"),
            argtypes=[c_char_p],
        )

    def _utf8(nsstr: Any) -> str:
        if not nsstr:
            return ""
        raw = _send(nsstr, "UTF8String", restype=c_char_p, argtypes=[])
        return raw.decode("utf-8") if raw else ""

    if _RESET_PANEL is None:
        panel = _send(objc.objc_getClass(b"NSPanel"), "alloc")
        panel = _send(panel, "init")
        if not panel:
            return
        mask = (1 << 0) | _NONACTIVATING_PANEL  # titled + nonactivating
        _send(panel, "setStyleMask:", mask, restype=None, argtypes=[c_ulong])
        _send(panel, "setTitle:", _nsstring(RESET_CONTROL_TITLE), argtypes=[c_void_p])
        _send(panel, "setLevel:", _FLOATING_LEVEL, restype=None, argtypes=[c_long])
        _send(panel, "setHidesOnDeactivate:", False, restype=None, argtypes=[c_bool])
        _send(panel, "setIgnoresMouseEvents:", False, restype=None, argtypes=[c_bool])
        _send(
            panel,
            "setCollectionBehavior:",
            _COLLECTION,
            restype=None,
            argtypes=[c_ulong],
        )
        _send(panel, "setContentSize:", _NSSize(150, 48), argtypes=[_NSSize])
        button = _send(objc.objc_getClass(b"NSButton"), "new")
        if not button:
            return
        _send(button, "setTitle:", _nsstring("Reset"), argtypes=[c_void_p])
        _send(button, "setButtonType:", _BUTTON_ON_OFF, restype=None, argtypes=[c_ulong])
        _send(button, "setBezelStyle:", _BEZEL_ROUNDED, restype=None, argtypes=[c_ulong])
        _send(button, "setFrameSize:", _NSSize(140, 40), argtypes=[_NSSize])
        _send(button, "setFrameOrigin:", _NSPoint(4, 4), argtypes=[_NSPoint])
        content = _send(panel, "contentView")
        if content:
            _send(content, "addSubview:", button, restype=None, argtypes=[c_void_p])
        _RESET_PANEL = panel
        _RESET_BUTTON = button

    panel = _RESET_PANEL
    frame_val = _send(window, "valueForKey:", _nsstring("frame"), argtypes=[c_void_p])
    parsed = parse_ns_frame(_utf8(_send(frame_val, "description")) if frame_val else "")
    if parsed:
        px, py, pw, ph = parsed
        _send(
            panel,
            "setFrameOrigin:",
            _NSPoint(px + max(8.0, pw - 158.0), py + max(8.0, ph - 54.0)),
            argtypes=[_NSPoint],
        )
    already_child = False
    children = _send(window, "childWindows")
    if children and panel:
        count = int(_send(children, "count", restype=c_ulong, argtypes=[]) or 0)
        for index in range(count):
            child = _send(
                children,
                "objectAtIndex:",
                index,
                argtypes=[c_ulong],
            )
            if child == panel:
                already_child = True
                break
    if not already_child:
        _send(
            window,
            "addChildWindow:ordered:",
            panel,
            _WINDOW_ABOVE,
            restype=None,
            argtypes=[c_void_p, c_long],
        )
    _send(panel, "orderFrontRegardless", restype=None, argtypes=[])


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
