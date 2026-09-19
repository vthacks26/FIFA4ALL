"""Pick the built-in Mac webcam. Never Continuity Camera / iPhone."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Sequence


PHONE_NAME_MARKERS = ("iphone", "ipad", "continuity", "desk view")
BUILTIN_NAME_MARKERS = ("macbook", "facetime", "built-in", "imac")


@dataclass(frozen=True)
class CameraDevice:
    index: int
    name: str
    unique_id: str = ""
    is_continuity: bool = False


def name_is_phone(name: str, is_continuity: bool = False) -> bool:
    if is_continuity:
        return True
    lower = name.lower()
    return any(marker in lower for marker in PHONE_NAME_MARKERS)


def name_is_builtin_mac(name: str, is_continuity: bool = False) -> bool:
    if name_is_phone(name, is_continuity):
        return False
    lower = name.lower()
    return any(marker in lower for marker in BUILTIN_NAME_MARKERS)


def select_builtin_mac_camera(devices: Sequence[CameraDevice]) -> CameraDevice:
    if not devices:
        raise RuntimeError("No AVFoundation video cameras were listed.")
    builtin = [d for d in devices if name_is_builtin_mac(d.name, d.is_continuity)]
    if builtin:
        return builtin[0]
    listing = ", ".join(f"{d.index}:{d.name!r}" for d in devices)
    raise RuntimeError(
        "Could not find a built-in Mac camera (MacBook / FaceTime). "
        f"Refusing iPhone/Continuity. Devices: {listing}"
    )


def list_avfoundation_devices() -> list[CameraDevice]:
    if sys.platform != "darwin":
        return []
    import ctypes
    from ctypes import c_bool, c_char_p, c_ulong, c_void_p

    objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
    objc.objc_getClass.restype = c_void_p
    objc.objc_getClass.argtypes = [c_char_p]
    objc.sel_registerName.restype = c_void_p
    objc.sel_registerName.argtypes = [c_char_p]
    ctypes.CDLL(
        "/System/Library/Frameworks/Foundation.framework/Foundation",
        mode=ctypes.RTLD_GLOBAL,
    )
    ctypes.CDLL(
        "/System/Library/Frameworks/AVFoundation.framework/AVFoundation",
        mode=ctypes.RTLD_GLOBAL,
    )

    def _sel(name: str) -> c_void_p:
        return objc.sel_registerName(name.encode("utf-8"))

    def _cls(name: str) -> c_void_p:
        return objc.objc_getClass(name.encode("utf-8"))

    def _send(obj: Any, selector: str, *args: Any, restype=c_void_p, argtypes=None):
        func = objc.objc_msgSend
        func.restype = restype
        extra = argtypes if argtypes is not None else [c_void_p] * len(args)
        func.argtypes = [c_void_p, c_void_p, *extra]
        return func(obj, _sel(selector), *args)

    def _utf8(nsstr: Any) -> str:
        if not nsstr:
            return ""
        raw = _send(nsstr, "UTF8String", restype=c_char_p, argtypes=[])
        return raw.decode("utf-8") if raw else ""

    media = _send(
        _cls("NSString"),
        "stringWithUTF8String:",
        b"vide",
        restype=c_void_p,
        argtypes=[c_char_p],
    )
    devices_ns = _send(
        _cls("AVCaptureDevice"),
        "devicesWithMediaType:",
        media,
        restype=c_void_p,
        argtypes=[c_void_p],
    )
    if not devices_ns:
        return []
    count = int(_send(devices_ns, "count", restype=c_ulong, argtypes=[]) or 0)
    found: list[CameraDevice] = []
    continuity_sel = _sel("isContinuityCamera")
    for index in range(count):
        dev = _send(
            devices_ns,
            "objectAtIndex:",
            index,
            restype=c_void_p,
            argtypes=[c_ulong],
        )
        if not dev:
            continue
        name = _utf8(_send(dev, "localizedName", restype=c_void_p, argtypes=[]))
        unique = _utf8(_send(dev, "uniqueID", restype=c_void_p, argtypes=[]))
        is_continuity = False
        responds = bool(
            _send(
                dev,
                "respondsToSelector:",
                continuity_sel,
                restype=c_bool,
                argtypes=[c_void_p],
            )
        )
        if responds:
            is_continuity = bool(
                _send(dev, "isContinuityCamera", restype=c_bool, argtypes=[])
            )
        found.append(
            CameraDevice(
                index=index,
                name=name,
                unique_id=unique,
                is_continuity=is_continuity,
            )
        )
    return found
