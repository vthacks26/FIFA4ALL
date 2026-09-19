"""Local HTTP bridge serving control state and video to the orientation UI.

Endpoints:

- `GET  /config`      thresholds and key mapping, so the UI draws truthful zones
- `GET  /events`      Server-Sent Events stream of the control state contract
- `GET  /stream.mjpg` multipart MJPEG of the tracked camera frames
- `POST /calibrate`   set the current nose position as neutral
- `POST /arm`         start sending real key events to the focused application
- `POST /disarm`      stop sending key events and release everything held
- `POST /mock`        drive the mock source from the frontend dev panel

Server-Sent Events and multipart MJPEG are both plain HTTP, so this needs no
third-party Python packages. Video and control state are separate streams
because a dropped video frame must never delay a control update.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import monotonic
from typing import Any, Callable

from bridge.source import ControlSource, MockSource, WebcamSource
from output.focus import frontmost_application, game_has_focus
from output.keyboard import QuartzKeyboard, build_keyboard
from output.session import InputSession
from tracking.controls import DIRECTION_KEYS

DEFAULT_PORT = 8765

# Only these origins may read bridge responses. The bridge binds to loopback,
# but loopback includes every tab the user has open, so a wildcard would let any
# page arm keyboard injection or read the webcam stream.
ALLOWED_ORIGINS = frozenset(
    {
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
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
                    "has_video": isinstance(self.hub.source, WebcamSource),
                    "keyboard_problem": QuartzKeyboard.permission_error(),
                }
            )
        elif self.path.startswith("/events"):
            self._send_events()
        elif self.path.startswith("/stream.mjpg"):
            self._send_mjpeg()
        else:
            self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        if self.path.startswith("/calibrate"):
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


def main() -> int:
    parser = argparse.ArgumentParser(description="FIFA4ALL orientation bridge server")
    parser.add_argument("--mock", action="store_true", help="run without a webcam")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument(
        "--overlay",
        action="store_true",
        help="float a look-axis window above the game for the player",
    )
    args = parser.parse_args()

    source: ControlSource = MockSource() if args.mock else WebcamSource(camera_index=args.camera)
    server, hub = build_server(source, args.port)
    hub.start()

    mode = "mock" if args.mock else "webcam"
    # Flushed explicitly: stdout is block-buffered when piped to a log file, and
    # the operator must not miss the permission warning before a demo.
    banner = [
        f"FIFA4ALL bridge ({mode}) on http://127.0.0.1:{args.port}",
        "  /config  /events  /stream.mjpg  POST /calibrate  POST /arm  POST /disarm",
        "  keyboard output starts DISARMED; arm it from the second monitor",
    ]
    problem = QuartzKeyboard.permission_error()
    if problem is not None:
        banner += ["", "  keyboard output unavailable:", f"  {problem}", ""]
    else:
        banner.append("  keyboard output verified: synthetic keys reach macOS")
    print("\n".join(banner), flush=True)

    # The HTTP server is threaded so the capture loop owns the main thread,
    # which macOS requires for any window drawing.
    threading.Thread(target=server.serve_forever, name="bridge-http", daemon=True).start()
    try:
        hub.run(on_frame=_build_overlay(hub) if args.overlay else None)
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        hub.stop()
        server.shutdown()
    return 0


def _build_overlay(hub: ControlHub) -> "Callable[[dict[str, object]], None]":
    """Render the player-facing look-axis window, if OpenCV is available."""

    import cv2  # type: ignore[import-not-found]

    from bridge.overlay_view import draw_overlay
    from output.focus import restore_game_focus
    from tracking.overlay import WINDOW_TITLE, decorate_overlay_window, poll_reset_click

    state_box: dict[str, bool] = {"decorated": False}

    def render(state: dict[str, object]) -> None:
        source = hub.source
        frame = getattr(source, "last_frame", None)
        if frame is None:
            return
        cv2.imshow(WINDOW_TITLE, draw_overlay(cv2, frame, state, source.thresholds))
        cv2.waitKey(1)
        if not state_box["decorated"]:
            # Must happen after the first imshow, once the window exists.
            state_box["decorated"] = decorate_overlay_window(WINDOW_TITLE)
            # Creating the window can take key focus even though the panel is
            # non-activating, which would stop keys reaching the game.
            restore_game_focus()
        if poll_reset_click():
            source.calibrate()

    return render


if __name__ == "__main__":
    raise SystemExit(main())
