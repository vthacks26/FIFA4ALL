"""Local HTTP bridge serving control state and video to the orientation UI.

Endpoints:

- `GET  /config`      thresholds and key mapping, so the UI draws truthful zones
- `GET  /events`      Server-Sent Events stream of the control state contract
- `GET  /stream.mjpg` multipart MJPEG of the tracked camera frames
- `POST /calibrate`   set the current nose position as neutral
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import monotonic
from typing import Any

from bridge.source import ControlSource, MockSource, WebcamSource
from tracking.controls import DIRECTION_KEYS

DEFAULT_PORT = 8765


class ControlHub:
    """Runs a control source on a worker thread and fans state out to clients.

    The latest state and frame are kept under a lock rather than queued, so a
    slow browser tab falls behind by dropping frames instead of adding latency.
    """

    def __init__(self, source: ControlSource) -> None:
        self.source = source
        self._lock = threading.Condition()
        self._state: dict[str, object] = {}
        self._frame: bytes | None = None
        self._sequence = 0
        self._error: str | None = None
        self._stopped = False

    def start(self) -> None:
        thread = threading.Thread(target=self._run, name="control-hub", daemon=True)
        thread.start()

    def _run(self) -> None:
        try:
            for state, frame in self.source.frames():
                if self._stopped:
                    return
                with self._lock:
                    self._state = state
                    if frame is not None:
                        self._frame = frame
                    self._sequence += 1
                    self._lock.notify_all()
        except Exception as exc:  # surfaced to the UI instead of dying silently
            with self._lock:
                self._error = f"{type(exc).__name__}: {exc}"
                self._sequence += 1
                self._lock.notify_all()

    def stop(self) -> None:
        self._stopped = True
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
        self.send_header("Access-Control-Allow-Origin", "*")
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


def build_server(source: ControlSource, port: int = DEFAULT_PORT) -> tuple[ThreadingHTTPServer, ControlHub]:
    hub = ControlHub(source)
    handler = type("BoundBridgeHandler", (BridgeHandler,), {"hub": hub})
    server = QuietThreadingHTTPServer(("127.0.0.1", port), handler)
    return (server, hub)


def main() -> int:
    parser = argparse.ArgumentParser(description="FIFA4ALL orientation bridge server")
    parser.add_argument("--mock", action="store_true", help="run without a webcam")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--camera", type=int, default=0)
    args = parser.parse_args()

    source: ControlSource = MockSource() if args.mock else WebcamSource(camera_index=args.camera)
    server, hub = build_server(source, args.port)
    hub.start()

    mode = "mock" if args.mock else "webcam"
    print(f"FIFA4ALL bridge ({mode}) on http://127.0.0.1:{args.port}")
    print("  /config  /events  /stream.mjpg  POST /calibrate")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        hub.stop()
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
