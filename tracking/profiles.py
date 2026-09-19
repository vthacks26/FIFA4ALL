"""Per-player control profiles on disk.

A profile is everything the game learned about one player: which movement
drives which action (`tracking.bindings`) and the per-user calibration values
`tracking.controls` measures (resting mouth opening, resting eye opening, the
calibrated nose centre, and any thresholds Phase 4 learns per channel).

The guiding rule of this module is that a profile never silently degrades.
For a player who can only shoot by winking, a profile that quietly resets to
the shipped defaults is worse than one that refuses to load: the game looks
fine and stops obeying them. So every failure here is loud and names both the
file and the problem, there are no bare excepts, and no field is ever dropped
or defaulted on load.

Standard library only. This module is imported in CI where mediapipe and
OpenCV are not installed, so it must not reach into `tracking.controls`
(which imports the tracking stack) - it only carries the values across.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from tracking.bindings import CHANNELS, BindingError, BindingMap

# Bump when the on-disk shape changes, and add the old number to KNOWN_VERSIONS
# with a migration in `_migrate`. A file written by a newer version than this
# one is refused rather than read, because a newer writer may mean something
# different by a field we think we understand.
SCHEMA_VERSION = 1

# Versions this module can read. Version 1 is the first, so there is nothing to
# migrate yet; `_migrate` is where an older payload gets lifted to the current
# shape when that changes.
KNOWN_VERSIONS = frozenset({1})

DEFAULT_PROFILE_DIR = Path("profiles")

# Profile names become filenames, so they are restricted rather than escaped:
# letters, digits, spaces, hyphens and underscores, starting and ending with an
# alphanumeric. That rejects "..", "/", "\", leading dots and absolute paths,
# which is what stops a name from escaping the profile directory. Rejecting is
# deliberate over slugifying - two players named "Joe/1" and "Joe 1" must not
# quietly collapse onto the same file.
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9 _-]{0,62}[A-Za-z0-9])?$")

_TOP_LEVEL_KEYS = frozenset(
    {"schema_version", "name", "display_name", "saved_at", "bindings", "calibration"}
)
_CALIBRATION_KEYS = frozenset(
    {"mouth_rest", "eye_rest", "nose_center", "channel_thresholds"}
)


class ProfileError(Exception):
    """Base class for every way loading or saving a profile can fail."""


class ProfileNameError(ProfileError):
    """Raised for a name that is not safe to use as a filename."""


class ProfileNotFoundError(ProfileError):
    """Raised when the named profile does not exist on disk."""


class ProfileVersionError(ProfileError):
    """Raised for a schema version this build cannot read."""


class ProfileCorruptError(ProfileError):
    """Raised for a file that exists but cannot be trusted.

    Covers unreadable JSON, wrong types, missing fields, unexpected fields and
    bindings that reference channels or actions this build does not have. The
    message always names the file and what specifically is wrong, because the
    person fixing it is usually looking at a file they hand-edited.
    """


@dataclass(frozen=True)
class ChannelThreshold:
    """A hysteresis pair learned for one channel by this player.

    Mirrors `GestureChannel.default_on` / `default_off`: `off` sits below `on`
    so a value hovering on the boundary cannot chatter, and a latch that is
    engaged always has somewhere to release to.
    """

    on: float
    off: float

    def __post_init__(self) -> None:
        if self.on <= 0:
            raise ValueError("threshold `on` must be positive")
        if self.off >= self.on:
            raise ValueError("threshold `off` must be below `on`")


@dataclass(frozen=True)
class Profile:
    """One player's saved control setup.

    Attributes:
        name: Filename stem, restricted by `_NAME_PATTERN`.
        display_name: Free text shown in the UI. Unrestricted, because it never
            touches the filesystem.
        bindings: Which channel drives each action.
        mouth_rest: Mouth-opening ratio measured while sitting neutral, as
            sampled by `ControlStateMachine.calibrate`. None means never
            measured, which is not the same as measured at zero.
        eye_rest: Eye-opening ratio measured the same way.
        nose_center: The calibrated neutral nose point, or None.
        channel_thresholds: Per-channel learned hysteresis, keyed by channel
            name. Phase 4 writes into this; an empty mapping means every
            channel still uses its shipped defaults.
        saved_at: When this profile was written. `save_profile` stamps the
            current time when this is None.
    """

    name: str
    display_name: str
    bindings: BindingMap
    mouth_rest: float | None = None
    eye_rest: float | None = None
    nose_center: tuple[float, float] | None = None
    channel_thresholds: Mapping[str, ChannelThreshold] = field(default_factory=dict)
    saved_at: datetime | None = None

    def __post_init__(self) -> None:
        # Validated here rather than only at save time so a Profile object can
        # never be holding a name that would escape the profile directory.
        validate_profile_name(self.name)
        for channel in self.channel_thresholds:
            if channel not in CHANNELS:
                raise BindingError(f"unknown channel in thresholds: {channel}")


def validate_profile_name(name: str) -> str:
    """Return `name` unchanged, or raise `ProfileNameError` explaining why not.

    Path traversal is blocked by the character set: a name containing a
    separator or a dot segment cannot match, so `os.path.join` can never walk
    out of the profile directory.
    """

    if not isinstance(name, str):
        raise ProfileNameError(f"profile name must be a string, got {type(name).__name__}")
    if not _NAME_PATTERN.fullmatch(name):
        raise ProfileNameError(
            f"invalid profile name {name!r}: use 1-64 letters, digits, spaces, "
            "hyphens or underscores, starting and ending with a letter or digit"
        )
    return name


def profile_path(name: str, *, directory: Path | str = DEFAULT_PROFILE_DIR) -> Path:
    """Where the named profile lives. Validates the name first."""

    return Path(directory) / f"{validate_profile_name(name)}.json"


def save_profile(profile: Profile, *, directory: Path | str = DEFAULT_PROFILE_DIR) -> Path:
    """Write `profile` to `<directory>/<name>.json` and return the path.

    Creates the directory if it is missing. The write goes to a temporary file
    in the same directory and is then renamed over the target, so a crash
    mid-write leaves the previous profile intact rather than a half-written
    file that would refuse to load next time.
    """

    target = profile_path(profile.name, directory=directory)
    target.parent.mkdir(parents=True, exist_ok=True)

    saved_at = profile.saved_at or datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "name": profile.name,
        "display_name": profile.display_name,
        "saved_at": saved_at.isoformat(),
        "bindings": profile.bindings.as_dict(),
        "calibration": {
            "mouth_rest": profile.mouth_rest,
            "eye_rest": profile.eye_rest,
            "nose_center": (
                None if profile.nose_center is None else list(profile.nose_center)
            ),
            "channel_thresholds": {
                channel: {"on": pair.on, "off": pair.off}
                for channel, pair in profile.channel_thresholds.items()
            },
        },
    }

    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    # delete=False because we rename the file into place rather than let the
    # context manager remove it.
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target.parent,
        prefix=f".{profile.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    os.replace(temp_path, target)
    return target


def load_profile(name: str, *, directory: Path | str = DEFAULT_PROFILE_DIR) -> Profile:
    """Read the named profile, or raise a `ProfileError` saying why not."""

    path = profile_path(name, directory=directory)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ProfileNotFoundError(f"no profile at {path}") from exc
    except OSError as exc:
        raise ProfileError(f"could not read {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ProfileCorruptError(f"{path} is not valid UTF-8 text: {exc}") from exc

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProfileCorruptError(
            f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}"
        ) from exc

    if not isinstance(payload, dict):
        raise ProfileCorruptError(
            f"{path} must contain a JSON object, found {type(payload).__name__}"
        )

    payload = _check_version(payload, path)
    _reject_unexpected(payload, _TOP_LEVEL_KEYS, path, "top level")

    stored_name = _require_str(payload, "name", path)
    if stored_name != name:
        # A renamed file is ambiguous: we cannot tell whether the player wanted
        # a copy under a new name or the rename was an accident, and guessing
        # either way risks loading the wrong person's controls.
        raise ProfileCorruptError(
            f"{path} stores name {stored_name!r} but was loaded as {name!r}; "
            "rename the file and the `name` field together"
        )

    calibration = payload.get("calibration")
    if not isinstance(calibration, dict):
        raise ProfileCorruptError(
            f"{path}: `calibration` must be an object, found "
            f"{type(calibration).__name__}"
        )
    _reject_unexpected(calibration, _CALIBRATION_KEYS, path, "calibration")

    return Profile(
        name=stored_name,
        display_name=_require_str(payload, "display_name", path),
        bindings=_read_bindings(payload, path),
        mouth_rest=_optional_float(calibration, "mouth_rest", path),
        eye_rest=_optional_float(calibration, "eye_rest", path),
        nose_center=_read_nose_center(calibration, path),
        channel_thresholds=_read_thresholds(calibration, path),
        saved_at=_read_saved_at(payload, path),
    )


def list_profiles(*, directory: Path | str = DEFAULT_PROFILE_DIR) -> tuple[str, ...]:
    """Names of the saved profiles, sorted.

    A missing directory means nobody has saved a profile yet, which is not an
    error. Files whose stem is not a valid profile name were not written by
    `save_profile` and could not be loaded by name, so they are left out.
    """

    folder = Path(directory)
    if not folder.is_dir():
        return ()
    names = []
    for entry in folder.glob("*.json"):
        if not entry.is_file():
            continue
        if _NAME_PATTERN.fullmatch(entry.stem):
            names.append(entry.stem)
    return tuple(sorted(names))


def _check_version(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    """Refuse versions we cannot read; migrate the ones we can."""

    version = payload.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ProfileCorruptError(
            f"{path}: `schema_version` must be an integer, found {version!r}"
        )
    if version > SCHEMA_VERSION:
        raise ProfileVersionError(
            f"{path} was written by a newer version of the app "
            f"(schema {version}, this build reads {SCHEMA_VERSION}). "
            "Update the app rather than editing the file - loading it here "
            "could apply the wrong controls."
        )
    if version not in KNOWN_VERSIONS:
        raise ProfileVersionError(
            f"{path}: unknown schema version {version}; "
            f"this build reads {sorted(KNOWN_VERSIONS)}"
        )
    return _migrate(payload, version)


def _migrate(payload: dict[str, Any], version: int) -> dict[str, Any]:
    """Lift an older payload to the current shape.

    Version 1 is the current and only version, so there is nothing to do yet.
    When SCHEMA_VERSION moves to 2, this is where a version 1 payload gains its
    new fields explicitly - never by letting a reader default them.
    """

    if version == SCHEMA_VERSION:
        return payload
    raise ProfileVersionError(  # pragma: no cover - unreachable while there is one version
        f"no migration from schema {version} to {SCHEMA_VERSION}"
    )


def _reject_unexpected(
    block: Mapping[str, Any], allowed: frozenset[str], path: Path, where: str
) -> None:
    """Fail on keys we do not understand at a version we claim to read.

    A newer writer is supposed to bump the schema version, so an unknown key at
    a known version means the file was hand-edited or written by something
    else. Ignoring it would be exactly the silent data loss this module exists
    to prevent.
    """

    unexpected = sorted(set(block) - allowed)
    if unexpected:
        raise ProfileCorruptError(
            f"{path}: unexpected {where} field(s) {unexpected}; "
            f"expected only {sorted(allowed)}"
        )


def _require_str(block: Mapping[str, Any], key: str, path: Path) -> str:
    if key not in block:
        raise ProfileCorruptError(f"{path}: missing required field `{key}`")
    value = block[key]
    if not isinstance(value, str):
        raise ProfileCorruptError(
            f"{path}: `{key}` must be a string, found {type(value).__name__}"
        )
    return value


def _optional_float(
    block: Mapping[str, Any], key: str, path: Path, where: str = "calibration"
) -> float | None:
    """Read a numeric value that may legitimately be null.

    The key must be present. A missing key is a corrupt file, not a null: null
    means "never measured", and we must not turn a measurement we failed to
    read into one. `where` names the enclosing block for the error message.
    """

    if key not in block:
        raise ProfileCorruptError(f"{path}: missing required field `{where}.{key}`")
    value = block[key]
    if value is None:
        return None
    # bool is a subclass of int, and `true` here is a sign of a broken writer.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileCorruptError(
            f"{path}: `{where}.{key}` must be a number or null, found {value!r}"
        )
    return float(value)


def _read_nose_center(
    calibration: Mapping[str, Any], path: Path
) -> tuple[float, float] | None:
    if "nose_center" not in calibration:
        raise ProfileCorruptError(f"{path}: missing required field `calibration.nose_center`")
    value = calibration["nose_center"]
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2:
        raise ProfileCorruptError(
            f"{path}: `calibration.nose_center` must be [x, y] or null, found {value!r}"
        )
    for component in value:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            raise ProfileCorruptError(
                f"{path}: `calibration.nose_center` must hold two numbers, found {value!r}"
            )
    return (float(value[0]), float(value[1]))


def _read_thresholds(
    calibration: Mapping[str, Any], path: Path
) -> dict[str, ChannelThreshold]:
    if "channel_thresholds" not in calibration:
        raise ProfileCorruptError(
            f"{path}: missing required field `calibration.channel_thresholds`"
        )
    raw = calibration["channel_thresholds"]
    if not isinstance(raw, dict):
        raise ProfileCorruptError(
            f"{path}: `calibration.channel_thresholds` must be an object, "
            f"found {type(raw).__name__}"
        )

    thresholds: dict[str, ChannelThreshold] = {}
    for channel, pair in raw.items():
        if channel not in CHANNELS:
            raise ProfileCorruptError(
                f"{path}: `calibration.channel_thresholds` names unknown channel "
                f"{channel!r}; known channels are {sorted(CHANNELS)}"
            )
        if not isinstance(pair, dict):
            raise ProfileCorruptError(
                f"{path}: threshold for {channel!r} must be an object with `on` "
                f"and `off`, found {type(pair).__name__}"
            )
        _reject_unexpected(pair, frozenset({"on", "off"}), path, f"threshold {channel!r}")
        where = f"channel_thresholds.{channel}"
        on = _optional_float(pair, "on", path, where)
        off = _optional_float(pair, "off", path, where)
        if on is None or off is None:
            raise ProfileCorruptError(
                f"{path}: threshold for {channel!r} needs both `on` and `off`"
            )
        try:
            thresholds[channel] = ChannelThreshold(on=on, off=off)
        except ValueError as exc:
            # A released latch needs off < on; a file that breaks that would
            # stick a key down in game, so say so instead of loading it.
            raise ProfileCorruptError(
                f"{path}: threshold for {channel!r} is unusable: {exc}"
            ) from exc
    return thresholds


def _read_bindings(payload: Mapping[str, Any], path: Path) -> BindingMap:
    if "bindings" not in payload:
        raise ProfileCorruptError(f"{path}: missing required field `bindings`")
    raw = payload["bindings"]
    if not isinstance(raw, dict):
        raise ProfileCorruptError(
            f"{path}: `bindings` must be an object, found {type(raw).__name__}"
        )
    for action, channel in raw.items():
        if not isinstance(channel, str):
            raise ProfileCorruptError(
                f"{path}: binding for {action!r} must be a channel name, found {channel!r}"
            )
    try:
        return BindingMap(bindings=dict(raw))
    except BindingError as exc:
        # BindingMap already says precisely what is wrong; all this adds is
        # which file said it. The original stays on __cause__.
        raise ProfileCorruptError(f"{path}: unusable bindings: {exc}") from exc


def _read_saved_at(payload: Mapping[str, Any], path: Path) -> datetime:
    raw = _require_str(payload, "saved_at", path)
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ProfileCorruptError(
            f"{path}: `saved_at` must be an ISO 8601 timestamp, found {raw!r}"
        ) from exc
