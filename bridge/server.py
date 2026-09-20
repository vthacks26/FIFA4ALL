"""Local HTTP bridge serving control state and video to the orientation UI.

Endpoints:

- `GET  /config`      thresholds, key mapping and the active action-to-gesture
                      bindings, so the UI draws truthful zones and follows rebinds
- `GET  /events`      Server-Sent Events stream of the control state contract
- `GET  /stream.mjpg` multipart MJPEG of the tracked camera frames
- `POST /calibrate`   set the current nose position as neutral
- `POST /arm`         start sending real key events to the focused application
- `POST /disarm`      stop sending key events and release everything held
- `POST /deadzone-mode` switch fixed vs follow deadzone on this process
- `POST /mock`        drive the mock source from the frontend dev panel

Server-Sent Events and multipart MJPEG are both plain HTTP, so this needs no
third-party Python packages. Video and control state are separate streams
because a dropped video frame must never delay a control update.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import subprocess
import sys
import threading
import traceback
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from urllib.parse import urlparse

from bridge.source import ControlSource, MockSource, WebcamSource
from output.focus import frontmost_application, game_has_focus
from output.keyboard import QuartzKeyboard, build_keyboard
from output.session import InputSession
from tracking.bindings import selectable_channels
from tracking.controls import DEADZONE_MODES, DIRECTION_KEYS, parse_deadzone_mode

DEFAULT_PORT = 8765
UI_DIST = Path(__file__).resolve().parent.parent / "onboarding" / "dist"
MACOS_OPEN = "/usr/bin/open"


def orientation_ui_url(port: int = DEFAULT_PORT) -> str:
    """Intro / welcome page served by this process (no Vite / npm run dev)."""

    return f"http://127.0.0.1:{port}/"


def wait_until_serving(port: int, timeout: float = 5.0) -> bool:
    """True once GET / answers, so the first browser load is not connection-refused."""

    url = orientation_ui_url(port)
    # Bypass HTTP(S)_PROXY so a machine proxy cannot hide localhost.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        try:
            with opener.open(url, timeout=0.25):
                return True
        except urllib.error.HTTPError:
            return True  # server answered (missing dist is still "up")
        except (OSError, urllib.error.URLError):
            sleep(0.05)
    return False


def macos_open_bin() -> str | None:
    """Return ``/usr/bin/open`` on macOS when that helper exists."""

    if sys.platform != "darwin":
        return None
    return MACOS_OPEN if Path(MACOS_OPEN).is_file() else None


def _open_with_macos_open(url: str, opener: str) -> tuple[bool, str | None]:
    """Launch *url* with macOS ``open(1)``. ``webbrowser.open`` often no-ops here."""

    try:
        completed = subprocess.run(
            [opener, url],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception as exc:
        return (False, f"{opener}: {exc}")
    if completed.returncode == 0:
        return (True, None)
    detail = (completed.stderr or completed.stdout or "").strip()
    reason = f"{opener} exited {completed.returncode}"
    if detail:
        reason = f"{reason}: {detail}"
    return (False, reason)


def _open_with_webbrowser(url: str) -> tuple[bool, str | None]:
    try:
        if webbrowser.open(url, new=1, autoraise=True):
            return (True, None)
        return (False, "webbrowser.open returned False")
    except Exception as exc:
        return (False, f"webbrowser.open: {exc}")


def open_url_in_default_browser(url: str) -> tuple[bool, str | None]:
    """Open *url* in the default browser.

    On macOS prefer ``/usr/bin/open <url>``. Python's ``webbrowser.open`` often
    returns True (or False) without actually launching a window.
    """

    opener = macos_open_bin()
    if opener is not None:
        opened, reason = _open_with_macos_open(url, opener)
        if opened:
            return (True, opener)
        fallback_ok, fallback_reason = _open_with_webbrowser(url)
        if fallback_ok:
            return (True, "webbrowser")
        parts = [part for part in (reason, fallback_reason) if part]
        return (False, "; ".join(parts) or "unknown error")
    opened, reason = _open_with_webbrowser(url)
    return (opened, None if opened else (reason or "unknown error"))


def open_orientation_ui(port: int = DEFAULT_PORT) -> bool:
    """Open the Welcome / intro page after the UI server is listening.

    Returns True if the platform accepted the open request. Never raises:
    a failed open must not take down inject.
    """

    url = orientation_ui_url(port)
    try:
        opened, detail = open_url_in_default_browser(url)
    except Exception as exc:  # never fail the live product over a browser helper
        print(
            f"Could not open the orientation UI automatically ({exc}). "
            f"Open {url} in your browser.",
            flush=True,
        )
        return False
    if opened:
        how = "with /usr/bin/open" if detail == MACOS_OPEN else "in your default browser"
        print(f"Opened the orientation Welcome page {how}: {url}", flush=True)
        return True
    reason = detail or "unknown error"
    print(
        f"Could not open the orientation UI automatically ({reason}). "
        f"Open {url} in your browser.",
        flush=True,
    )
    return False


def maybe_open_orientation_ui(*, preview: bool, port: int) -> bool:
    """Open the intro page only for ``--preview``.

    ``--no-preview`` still serves the same URL, but must not steal keyboard
    focus from Luna by raising a browser.
    """

    if not preview:
        return False
    return open_orientation_ui(port)

# Only these origins may read bridge responses. The bridge binds to loopback,
# but loopback includes every tab the user has open, so a wildcard would let any
# page arm keyboard injection or read the webcam stream.
ALLOWED_ORIGINS = frozenset(
    {
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        # Same process serves the built UI here. The original onboarding
        # camera <img> always requested http://127.0.0.1:8765/stream.mjpg.
        "http://localhost:8765",
        "http://127.0.0.1:8765",
    }
)


class ControlHub:
    """Runs a control source on a worker thread and fans state out to clients.

    The latest state and frame are kept under a lock rather than queued, so a
    slow browser tab falls behind by dropping frames instead of adding latency.
    """

    # Listing on-screen windows is not free, so the frontmost application is
    # sampled a few times a second rather than on every tracked frame.
    FOCUS_POLL_SECONDS = 1.0

    def __init__(self, source: ControlSource, session: InputSession) -> None:
        self.source = source
        self.session = session
        self._focus: str | None = None
        self._focus_checked_at = 0.0
        self._lock = threading.Condition()
        self._state: dict[str, object] = {}
        self._frame: bytes | None = None
        self._sequence = 0
        self._error: str | None = None
        self._stopped = False

    def start(self) -> None:
        """Run the capture loop on a background thread."""

        thread = threading.Thread(target=self.run, name="control-hub", daemon=True)
        thread.start()

    def run(self, on_frame: "Callable[[dict[str, object]], None] | None" = None) -> None:
        """Run the capture loop on the calling thread.

        `on_frame` is called with each published state. macOS requires window
        drawing to happen on the main thread, so the overlay is rendered here
        rather than from a worker.
        """

        try:
            for state, frame in self.source.frames():
                if self._stopped:
                    return
                # Drive the real keyboard before publishing, so the UI never
                # shows a state the game has not already been sent.
                self.session.apply(state)
                state = {**state, **self._match_status()}
                with self._lock:
                    self._state = state
                    if frame is not None:
                        self._frame = frame
                    self._sequence += 1
                    self._lock.notify_all()
                if on_frame is not None:
                    on_frame(state)
        except Exception as exc:  # surfaced to the UI instead of dying silently
            # Also print it: the capture loop ending stops the whole bridge, and
            # an operator watching the console should not have to attach an SSE
            # client to find out why it stopped.
            traceback.print_exc()
            with self._lock:
                self._error = f"{type(exc).__name__}: {exc}"
                self._sequence += 1
                self._lock.notify_all()

    def _match_status(self) -> dict[str, object]:
        """Input-layer facts the second monitor needs during a match."""

        now = monotonic()
        if now - self._focus_checked_at >= self.FOCUS_POLL_SECONDS:
            self._focus = frontmost_application()
            self._focus_checked_at = now
        return {
            "armed": self.session.armed,
            "held_keys": sorted(self.session.held_keys),
            "shot_seconds": round(self.session.shot_seconds, 3),
            "frontmost": self._focus,
            "game_focus": game_has_focus(self._focus),
        }

    def stop(self) -> None:
        self._stopped = True
        self.session.disarm()
        self.source.stop()
        with self._lock:
            self._lock.notify_all()

    def wait_for_update(self, last_seen: int, timeout: float = 5.0) -> tuple[int, dict[str, object], bytes | None, str | None]:
        with self._lock:
            if self._sequence == last_seen:
                self._lock.wait(timeout)
            return (self._sequence, dict(self._state), self._frame, self._error)


class BridgeHandler(BaseHTTPRequestHandler):
    hub: ControlHub
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        return  # keep the demo console readable

    def _cors(self) -> None:
        """Echo the origin only when it is one we trust.

        A request with no Origin header is same-origin or a direct client such
        as curl, which the browser does not gate, so nothing is sent.
        """

        origin = self.headers.get("Origin")
        if origin is None:
            return
        if origin not in ALLOWED_ORIGINS:
            return
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.startswith("/config"):
            self._send_json(
                {
                    "thresholds": self.hub.source.thresholds.as_dict(),
                    "direction_keys": {k: list(v) for k, v in DIRECTION_KEYS.items()},
                    # The live action -> channel map, so a drill or a meter
                    # labels itself from the binding actually in force rather
                    # than from a gesture name compiled into the UI.
                    "bindings": self.hub.source.machine.bindings.as_dict(),
                    # Every channel orientation may offer, with the wording the
                    # UI should use to ask for it. Only `selectable` channels
                    # appear: a channel that has not cleared the eligibility
                    # rule still works when bound but is never proposed.
                    "channels": [
                        {"name": channel.name, "label": channel.label}
                        for channel in selectable_channels()
                    ],
                    "has_video": isinstance(self.hub.source, WebcamSource),
                    "keyboard_problem": QuartzKeyboard.permission_error(),
                    "deadzone_mode": self.hub.source.machine.deadzone_mode,
                }
            )
        elif self.path.startswith("/events"):
            self._send_events()
        elif self.path.startswith("/stream.mjpg"):
            self._send_mjpeg()
        else:
            self._send_static()

    def do_POST(self) -> None:
        if self.path.startswith("/calibrate"):
            # Same ControlSource the Quartz injector is already reading.
            self.hub.source.calibrate()
            self._send_json({"ok": True})
        elif self.path.startswith("/arm"):
            problem = QuartzKeyboard.permission_error()
            if problem is not None:
                self._send_json({"error": problem}, status=409)
                return
            self.hub.session.arm()
            self._send_json({"ok": True, "armed": True})
        elif self.path.startswith("/disarm"):
            self.hub.session.disarm()
            self._send_json({"ok": True, "armed": False})
        elif self.path.startswith("/mock"):
            payload = self._read_json()
            source = self.hub.source
            if isinstance(source, MockSource):
                source.set_override(payload)
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "server is not running a mock source"}, status=409)
        elif self.path.startswith("/deadzone-mode"):
            payload = self._read_json() or {}
            try:
                mode = self.hub.source.set_deadzone_mode(payload.get("mode"))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json({"ok": True, "deadzone_mode": mode})
        else:
            self._send_json({"error": "not found"}, status=404)

    def _read_json(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return None
        try:
            decoded = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return decoded if isinstance(decoded, dict) else None

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_events(self) -> None:
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        seen = -1
        try:
            while True:
                seen, state, _frame, error = self.hub.wait_for_update(seen)
                payload = {"error": error} if error else state
                if not payload:
                    continue
                self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return  # browser navigated away

    def _send_mjpeg(self) -> None:
        boundary = "fifa4allframe"
        self.send_response(200)
        self._cors()
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={boundary}")
        self.end_headers()
        seen = -1
        try:
            while True:
                seen, _state, frame, error = self.hub.wait_for_update(seen)
                if error or frame is None:
                    continue
                self.wfile.write(f"--{boundary}\r\n".encode("ascii"))
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii"))
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_static(self) -> None:
        parsed = urlparse(self.path)
        rel = parsed.path.lstrip("/")
        root = UI_DIST.resolve()
        if not rel or rel == "index.html":
            target = root / "index.html"
        else:
            target = (root / rel).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                self._send_json({"error": "not found"}, status=404)
                return
        if not target.is_file():
            fallback = root / "index.html"
            if fallback.is_file():
                target = fallback
            else:
                self._send_json(
                    {
                        "error": "orientation UI is not built",
                        "hint": "cd onboarding && npm install && npm run build",
                    },
                    status=404,
                )
                return
        data = target.read_bytes()
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    """HTTP server that does not log a traceback when a client disconnects.

    Browsers drop long-lived MJPEG and SSE connections whenever a tab closes or
    reloads, which is normal here and must not spam the demo console.
    """

    daemon_threads = True

    def handle_error(self, request: object, client_address: object) -> None:
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)  # type: ignore[arg-type]


def build_server(
    source: ControlSource,
    port: int = DEFAULT_PORT,
    session: InputSession | None = None,
) -> tuple[ThreadingHTTPServer, ControlHub]:
    hub = ControlHub(source, session or InputSession(build_keyboard()))
    handler = type("BoundBridgeHandler", (BridgeHandler,), {"hub": hub})
    server = QuietThreadingHTTPServer(("127.0.0.1", port), handler)
    return (server, hub)


def run_product(
    *,
    preview: bool,
    port: int = DEFAULT_PORT,
    mock: bool = False,
    armed: bool = True,
    deadzone_mode: str = "fixed",
) -> int:
    """One process: MacBook camera, Quartz holds, overlay, orientation UI."""

    if mock:
        source: ControlSource = MockSource()
        session = InputSession(build_keyboard(), armed=False)
        camera_line = "mock (no camera)"
    else:
        from tracking.mac_camera import (
            list_avfoundation_devices,
            select_builtin_mac_camera,
            skipped_phone_devices,
        )

        devices = list_avfoundation_devices()
        listing = ", ".join(f"{d.index}:{d.name!r}" for d in devices) or "(none)"
        print(f"AVFoundation cameras: {listing}", flush=True)
        for phone in skipped_phone_devices(devices):
            print(
                f"Skipping iPhone/Continuity index={phone.index} name={phone.name!r} "
                "(will not probe)",
                flush=True,
            )
        try:
            chosen = select_builtin_mac_camera(devices)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(
            f"Using built-in Mac camera index={chosen.index} name={chosen.name!r} "
            "(refusing iPhone/Continuity; opening this named index only)",
            flush=True,
        )
        source = WebcamSource(
            camera_index=chosen.index,
            camera_name=chosen.name,
            camera_unique_id=chosen.unique_id,
        )
        session = InputSession(build_keyboard(), armed=armed)
        camera_line = f"{chosen.index}:{chosen.name!r}"

    source.set_deadzone_mode(deadzone_mode)
    server, hub = build_server(source, port, session)
    bound_port = int(server.server_address[1])
    intro = orientation_ui_url(bound_port)
    banner = [
        f"FIFA4ALL live on {intro}  camera={camera_line}",
        "  same process: Quartz WASD / Space hold / wink-L hold",
        "  overlay RESET, raised eyebrows, and POST /calibrate recapture neutral",
        f"  deadzone={source.machine.deadzone_mode} "
        "(overlay FIXED/FOLLOW switch; default fixed-center)",
    ]
    if preview:
        banner.append(
            "  --preview waits until the UI is listening, then opens the Welcome "
            "page (macOS: /usr/bin/open). The look-axis window stays a separate "
            "camera/vision overlay — not website chrome. No npm run dev."
        )
    else:
        banner.append(
            "  --no-preview still serves that URL but does not open a browser, "
            "so Luna can keep keyboard focus"
        )
    if not mock:
        banner.append(
            "  inject starts ARMED; the orientation HUD can disarm without "
            "opening another camera"
        )
    print("\n".join(banner), flush=True)

    threading.Thread(target=server.serve_forever, name="bridge-http", daemon=True).start()
    if preview:
        ready = wait_until_serving(bound_port)
        if not ready:
            print(
                f"Could not confirm the orientation UI is listening at {intro}. "
                f"Open {intro} in your browser once it is up.",
                flush=True,
            )
        else:
            maybe_open_orientation_ui(preview=True, port=bound_port)
    try:
        hub.run(on_frame=_build_overlay(hub) if preview else None)
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        hub.stop()
        server.shutdown()
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="FIFA4ALL live product (alias of python -m tracking.live)"
    )
    parser.add_argument("--mock", action="store_true", help="UI-only mock; no webcam")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--preview",
        action="store_true",
        help=(
            "after the UI is listening, open the Welcome page "
            "(macOS: /usr/bin/open) and show the separate camera overlay"
        ),
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="inject + serve the UI without overlay or opening a browser (keeps Luna focused)",
    )
    parser.add_argument(
        "--overlay",
        action="store_true",
        help="same as --preview (kept for older scripts)",
    )
    parser.add_argument(
        "--deadzone-mode",
        choices=DEADZONE_MODES,
        default="fixed",
        help=(
            "fixed (default): deadzone stays on the calibrated center. "
            "follow: further look pulls the deadzone so a small opposite move stops. "
            "The overlay FIXED/FOLLOW switch can still change this at runtime."
        ),
    )
    args = parser.parse_args(argv)
    preview = (bool(args.preview) or bool(args.overlay)) and not bool(args.no_preview)
    mode = parse_deadzone_mode(args.deadzone_mode)
    if args.mock:
        return run_product(
            preview=preview, port=args.port, mock=True, armed=False, deadzone_mode=mode
        )
    print(
        "Starting the live product "
        f"(python -m tracking.live {'--preview' if preview else '--no-preview'})",
        flush=True,
    )
    return run_product(
        preview=preview, port=args.port, mock=False, armed=True, deadzone_mode=mode
    )


def _build_overlay(hub: ControlHub) -> "Callable[[dict[str, object]], None]":
    """Render the player-facing look-axis window, if OpenCV is available."""

    import cv2  # type: ignore[import-not-found]

    from bridge.overlay_view import apply_overlay_click, draw_overlay
    from output.focus import restore_game_focus
    from tracking.overlay import (
        WINDOW_TITLE,
        decorate_overlay_window,
        poll_mode_click,
        poll_reset_click,
    )

    state_box: dict[str, bool] = {"decorated": False, "mouse": False}

    def _on_mouse(event: int, x: int, y: int, *_args: object) -> None:
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        frame = getattr(hub.source, "last_frame", None)
        if frame is None:
            return
        height, width = frame.shape[:2]
        action = apply_overlay_click(hub.source, x, y, width, height)
        if action in ("fixed", "follow"):
            print(f"Deadzone: {action} (overlay switch)", flush=True)

    def render(state: dict[str, object]) -> None:
        source = hub.source
        frame = getattr(source, "last_frame", None)
        if frame is None:
            return
        cv2.imshow(WINDOW_TITLE, draw_overlay(cv2, frame, state, source.thresholds))
        if not state_box["mouse"]:
            cv2.setMouseCallback(WINDOW_TITLE, _on_mouse)
            state_box["mouse"] = True
        cv2.waitKey(1)
        if not state_box["decorated"]:
            # Must happen after the first imshow, once the window exists.
            state_box["decorated"] = decorate_overlay_window(WINDOW_TITLE)
            # Creating the window can take key focus even though the panel is
            # non-activating, which would stop keys reaching the game.
            restore_game_focus()
        if poll_reset_click():
            source.calibrate()
        mode = poll_mode_click()
        if mode is not None:
            source.set_deadzone_mode(mode)
            print(f"Deadzone: {mode} (overlay switch)", flush=True)

    return render


if __name__ == "__main__":
    raise SystemExit(main())
