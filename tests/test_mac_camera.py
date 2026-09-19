import pytest

from fifa4all.vision.mac_camera import (
    CameraDevice,
    name_is_phone,
    select_builtin_mac_camera,
)


def test_selects_macbook_over_iphone():
    devices = [
        CameraDevice(0, "iPhone Camera", is_continuity=True),
        CameraDevice(1, "MacBook Pro Camera"),
    ]
    chosen = select_builtin_mac_camera(devices)
    assert chosen.index == 1
    assert chosen.name == "MacBook Pro Camera"


def test_refuses_iphone_only():
    devices = [CameraDevice(0, "iPhone (33) Camera", is_continuity=True)]
    with pytest.raises(RuntimeError, match="iPhone|Continuity|built-in"):
        select_builtin_mac_camera(devices)


def test_phone_name_markers():
    assert name_is_phone("iPhone Camera", False)
    assert name_is_phone("Desk View", False)
    assert name_is_phone("Continuity Camera", True)
    assert not name_is_phone("MacBook Pro Camera", False)


def test_facetime_preferred_when_iphone_is_index_zero():
    devices = [
        CameraDevice(0, "iPhone", is_continuity=True),
        CameraDevice(1, "FaceTime HD Camera"),
    ]
    chosen = select_builtin_mac_camera(devices)
    assert chosen.index == 1
    assert chosen.name == "FaceTime HD Camera"
