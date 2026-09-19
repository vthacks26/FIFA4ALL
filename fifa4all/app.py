"""FIFA4ALL CLI: camera or headless replay → OS key holds."""

from __future__ import annotations

import argparse
import atexit
import signal
import sys
import time
from typing import Sequence

from fifa4all.config import Config
from fifa4all.controls.intent import GestureEngine
from fifa4all.output.keyboard import (
    HeldKeySession,
    LoggingKeyInjector,
    RecordingKeyInjector,
    create_injector,
)
from fifa4all.output.permissions import MACOS_PERMISSION_HELP, accessibility_trusted, is_macos
from fifa4all.replay import config_with_payload, load_replay, run_feature_frames
from fifa4all.vision.features import extract_features


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fifa4all",
        description=(
            "Map head/face motion to WASD / Space / L using OS-level key events "
            "for EA Sports FC on Amazon Luna in Google Chrome."
        ),
    )
    p.add_argument(
        "--injector",
        default="auto",
        choices=("auto", "quartz", "pynput", "recording", "dry-run"),
        help="auto uses Quartz HID events on macOS; dry-run/recording never post keys",
    )
    p.add_argument("--camera", type=int, default=0, help="Webcam index")
    p.add_argument("--no-mirror", action="store_true", help="Disable mirrored webcam")
    p.add_argument("--no-preview", action="store_true", help="Do not open an OpenCV window")
    p.add_argument(
        "--calibrate-seconds",
        type=float,
        default=2.0,
        help="Hold a neutral face this long at startup",
    )
    p.add_argument(
        "--ready-delay",
        type=float,
        default=None,
        help="Seconds to wait (after calibration) so you can click Chrome. Default 5 on macOS live injectors",
    )
    p.add_argument("--replay", help="JSON feature-frame file (headless, no camera)")
    p.add_argument(
        "--key-smoke",
        action="store_true",
        help="Send a canned WASD/Space/L hold sequence (no camera). Focus Chrome first.",
    )
    p.add_argument("--print-events", action="store_true", help="Print recorded injector events")
    return p


def _ready_delay(args: argparse.Namespace) -> float:
    if args.ready_delay is not None:
        return max(0.0, args.ready_delay)
    live = args.injector in {"auto", "quartz", "pynput"} and not args.replay
    if is_macos() and live and not args.key_smoke:
        return 5.0
    if args.key_smoke and args.injector in {"auto", "quartz", "pynput"}:
        return 5.0 if args.ready_delay is None else args.ready_delay
    return 0.0


def _install_release_handler(session: HeldKeySession) -> None:
    def _stop(*_args: object) -> None:
        session.release_all()
        sys.exit(0)

    atexit.register(session.release_all)
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)


def _warn_permissions(injector_kind: str) -> None:
    live = injector_kind in {"auto", "quartz", "pynput"}
    if not live:
        return
    if not is_macos():
        print(
            "WARNING: Live OS injection on this host is not the target. "
            "Target is Google Chrome on a Mac. Use --injector dry-run or "
            "--replay here. Quartz HID injection runs only on macOS.",
            file=sys.stderr,
        )
        return
    trusted = accessibility_trusted()
    if trusted is False:
        print("Accessibility is NOT granted for this process.", file=sys.stderr)
        print(MACOS_PERMISSION_HELP, file=sys.stderr)
    elif trusted is True:
        print("Accessibility appears granted for this process.")
    print(
        "OS keys go to the frontmost app. Click the Google Chrome Luna window "
        "before holds begin.",
        file=sys.stderr,
    )


def _countdown(seconds: float, label: str) -> None:
    if seconds <= 0:
        return
    end = time.monotonic() + seconds
    print(label, flush=True)
    while True:
        left = end - time.monotonic()
        if left <= 0:
            break
        print(f"  {left:0.1f}s …", flush=True)
        time.sleep(min(0.5, left))


def run_key_smoke(injector, delay: float, print_events: bool) -> int:
    session = HeldKeySession(injector)
    _install_release_handler(session)
    _countdown(
        delay,
        "KEY SMOKE: click Google Chrome (Luna / EA FC) so it is focused.",
    )
    sequence: list[tuple[float, set[str]]] = [
        (0.15, set()),
        (0.40, {"w"}),
        (0.15, set()),
        (0.40, {"a"}),
        (0.15, set()),
        (0.40, {"s"}),
        (0.15, set()),
        (0.40, {"d"}),
        (0.15, set()),
        (0.40, {"w", "d"}),
        (0.15, set()),
        (0.80, {"space"}),  # hold — shot strength
        (0.15, set()),
        (0.50, {"l"}),  # hold — pass strength
        (0.15, set()),
    ]
    try:
        for hold_s, keys in sequence:
            session.apply(keys)
            label = " ".join(sorted(keys)).upper() if keys else "(none)"
            print(f"holding {label} for {hold_s:.2f}s", flush=True)
            time.sleep(hold_s)
    finally:
        session.release_all()
    if print_events and hasattr(injector, "events"):
        for ev in injector.events:
            print(f"{ev.time_s:.3f} {ev.action:4s} {ev.key}")
    print("Key smoke finished. Luna-on-Mac behavior is NOT verified from this environment.")
    return 0


def run_replay(path: str, injector, print_events: bool, config: Config) -> int:
    payload = load_replay(path)
    config = config_with_payload(config, payload)
    dt = float(payload.get("dt_sec", 1.0 / 30.0))
    frames = payload["frames"]
    calibrate_first = int(payload.get("calibrate_first", 0))
    intents = run_feature_frames(
        frames,
        injector,
        config=config,
        dt_sec=dt,
        calibrate_first=calibrate_first,
    )
    last = intents[-1] if intents else None
    print(f"Replay {path}: {len(intents)} frames, last keys={last.held_keys() if last else set()}")
    if print_events and hasattr(injector, "events"):
        for ev in injector.events:
            print(f"{ev.time_s:.3f} {ev.action:4s} {ev.key}")
    return 0


def run_camera(args: argparse.Namespace, injector, config: Config) -> int:
    from fifa4all.ui.overlay import draw_overlay
    from fifa4all.vision.camera import Webcam
    from fifa4all.vision.landmarks import MediaPipeFaceTracker

    session = HeldKeySession(injector)
    _install_release_handler(session)
    engine = GestureEngine(config)

    preview = not args.no_preview
    if preview:
        print(
            "Preview window may steal focus. After it opens, click Google Chrome "
            "so Luna receives keys. Or rerun with --no-preview.",
            file=sys.stderr,
        )

    tracker = MediaPipeFaceTracker(
        min_detection_confidence=config.min_detection_confidence,
        min_tracking_confidence=config.min_tracking_confidence,
    )
    cam = Webcam(index=args.camera, mirror=not args.no_mirror)

    import cv2

    try:
        print("Look at the camera with a NEUTRAL face for calibration.", flush=True)
        t0 = time.monotonic()
        while time.monotonic() - t0 < config.calibrate_seconds:
            frame = cam.read()
            if frame is None:
                continue
            obs = tracker.process(frame)
            feat = extract_features(obs.landmarks)
            engine.add_calibration_sample(feat)
            if preview:
                vis = draw_overlay(frame, feat, engine.update(feat), engine, status="CALIBRATING")
                engine.reset()
                cv2.imshow("FIFA4ALL", vis)
                if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                    return 0
        engine.finish_calibration()
        print(
            f"Calibrated yaw={engine.neutral_yaw:+.3f} pitch={engine.neutral_pitch:+.3f} "
            f"mouth={engine.neutral_mouth:.3f}",
            flush=True,
        )

        delay = _ready_delay(args)
        _countdown(delay, "Click the Google Chrome Luna window NOW.")

        print("Running. q or ESC quits. Face lost → all keys released.", flush=True)
        while True:
            frame = cam.read()
            if frame is None:
                session.release_all()
                time.sleep(0.02)
                continue
            obs = tracker.process(frame)
            feat = extract_features(obs.landmarks)
            intent = engine.update(feat)
            session.apply(intent.held_keys())
            if preview:
                vis = draw_overlay(frame, feat, intent, engine, status="LIVE")
                cv2.imshow("FIFA4ALL", vis)
                if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                    break
    finally:
        session.release_all()
        cam.close()
        tracker.close()
        if preview:
            cv2.destroyAllWindows()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = Config(
        calibrate_seconds=args.calibrate_seconds,
        camera_index=args.camera,
        mirror=not args.no_mirror,
        ready_delay_seconds=_ready_delay(args),
    )

    if args.replay or args.injector in {"recording", "dry-run"}:
        pass
    else:
        _warn_permissions(args.injector)

    if args.replay and args.injector == "auto":
        injector = RecordingKeyInjector()
    elif args.key_smoke and args.injector == "auto" and not is_macos():
        injector = LoggingKeyInjector()
    else:
        injector = create_injector(args.injector)

    if args.key_smoke:
        delay = args.ready_delay if args.ready_delay is not None else (
            5.0 if is_macos() and args.injector in {"auto", "quartz", "pynput"} else 0.0
        )
        return run_key_smoke(injector, delay, args.print_events)

    if args.replay:
        return run_replay(args.replay, injector, args.print_events, config)

    if args.injector == "auto" and not is_macos():
        print(
            "Refusing live camera injection on non-macOS. "
            "Use --replay, --key-smoke --injector dry-run, or run on a Mac.",
            file=sys.stderr,
        )
        return 2

    return run_camera(args, injector, config)


if __name__ == "__main__":
    raise SystemExit(main())
