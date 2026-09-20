"""Tests for the orientation bridge server and its control sources."""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from time import sleep

from bridge.server import build_server
from bridge.source import MockSource
from output.keyboard import RecordingKeyboard
from output.session import InputSession
from tracking.bindings import selectable_channels


def post(url: str, payload: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else b"{}"
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return (response.status, json.loads(response.read()))
    except urllib.error.HTTPError as error:
        return (error.code, json.loads(error.read()))


class MockSourceTests(unittest.TestCase):
    def test_scripted_loop_produces_valid_state(self) -> None:
        frames = MockSource().frames()
        state, image = next(frames)
        self.assertIsNone(image, "mock source has no video")
        self.assertLessEqual(
            {"centered", "nose", "direction", "keys", "mouth", "wink", "tracking"},
            set(state),
        )

    def test_override_drives_direction_and_keys(self) -> None:
        source = MockSource()
        frames = source.frames()
        next(frames)
        source.set_override({"tracking": True, "nose": {"x": 0.0, "y": -0.12}, "mouth": 0.0, "wink": 0.0})
        state, _ = next(frames)
        self.assertEqual(state["direction"], "N")
        self.assertEqual(state["keys"], ["W"])

    def test_override_can_simulate_tracking_loss(self) -> None:
        source = MockSource()
        frames = source.frames()
        next(frames)
        source.set_override({"tracking": False})
        state, _ = next(frames)
        self.assertFalse(state["tracking"])
        self.assertEqual(state["keys"], [])

    def test_clearing_the_override_returns_to_the_scripted_loop(self) -> None:
        source = MockSource()
        frames = source.frames()
        source.set_override({"tracking": False})
        next(frames)
        source.set_override(None)
        state, _ = next(frames)
        self.assertTrue(state["tracking"])


class BridgeServerTests(unittest.TestCase):
    server: ThreadingHTTPServer

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = MockSource()
        # A recording keyboard guarantees the suite can never press a real key.
        cls.keyboard = RecordingKeyboard()
        cls.server, cls.hub = build_server(
            cls.source, port=0, session=InputSession(cls.keyboard)
        )
        cls.port = cls.server.server_address[1]
        cls.hub.start()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.hub.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def test_config_publishes_thresholds_for_truthful_visualization(self) -> None:
        with urllib.request.urlopen(self.url("/config"), timeout=5) as response:
            config = json.loads(response.read())
        self.assertEqual(config["thresholds"]["enter_radius"], self.source.thresholds.enter_radius)
        self.assertEqual(config["thresholds"]["exit_radius"], self.source.thresholds.exit_radius)

    def test_config_publishes_the_direction_key_mapping(self) -> None:
        with urllib.request.urlopen(self.url("/config"), timeout=5) as response:
            config = json.loads(response.read())
        self.assertEqual(config["direction_keys"]["NE"], ["W", "D"])
        self.assertEqual(config["direction_keys"]["W"], ["A"])

    def test_config_publishes_the_active_binding_map(self) -> None:
        with urllib.request.urlopen(self.url("/config"), timeout=5) as response:
            config = json.loads(response.read())
        self.assertEqual(config["bindings"], self.source.machine.bindings.as_dict())

    def test_config_publishes_the_channels_the_ui_may_offer(self) -> None:
        with urllib.request.urlopen(self.url("/config"), timeout=5) as response:
            config = json.loads(response.read())
        by_name = {c["name"]: c["label"] for c in config["channels"]}
        self.assertEqual(
            by_name, {c.name: c.label for c in selectable_channels()}
        )

    def test_every_bound_channel_is_one_the_config_describes(self) -> None:
        """A UI following the map must find a label for whatever is bound."""

        with urllib.request.urlopen(self.url("/config"), timeout=5) as response:
            config = json.loads(response.read())
        names = {c["name"] for c in config["channels"]}
        for channel in config["bindings"].values():
            self.assertIn(channel, names)

    def test_mock_source_reports_no_video(self) -> None:
        with urllib.request.urlopen(self.url("/config"), timeout=5) as response:
            self.assertFalse(json.loads(response.read())["has_video"])

    def test_unknown_path_returns_404(self) -> None:
        status, _ = post(self.url("/nope"))
        self.assertEqual(status, 404)

    def test_calibrate_endpoint_accepts_the_request(self) -> None:
        status, body = post(self.url("/calibrate"))
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_config_publishes_the_deadzone_mode(self) -> None:
        with urllib.request.urlopen(self.url("/config"), timeout=5) as response:
            config = json.loads(response.read())
        self.assertEqual(config["deadzone_mode"], "fixed")

    def test_deadzone_mode_endpoint_switches_the_live_machine(self) -> None:
        try:
            status, body = post(self.url("/deadzone-mode"), {"mode": "follow"})
            self.assertEqual(status, 200)
            self.assertEqual(body["deadzone_mode"], "follow")
            self.assertEqual(self.source.machine.deadzone_mode, "follow")
            with urllib.request.urlopen(self.url("/config"), timeout=5) as response:
                self.assertEqual(json.loads(response.read())["deadzone_mode"], "follow")
        finally:
            post(self.url("/deadzone-mode"), {"mode": "fixed"})

    def test_deadzone_mode_endpoint_rejects_unknown_values(self) -> None:
        status, body = post(self.url("/deadzone-mode"), {"mode": "sticky"})
        self.assertEqual(status, 400)
        self.assertIn("deadzone_mode", str(body.get("error", "")))
        self.assertEqual(self.source.machine.deadzone_mode, "fixed")

    def test_follow_deadzone_releases_injected_keys_on_a_short_return(self) -> None:
        """Website toggle must change the same machine InputSession reads."""

        self.hub.session.arm()
        try:
            self.reset_center()
            post(self.url("/deadzone-mode"), {"mode": "follow"})
            post(
                self.url("/mock"),
                {"tracking": True, "nose": {"x": 0.20, "y": 0.0}, "mouth": 0.0, "wink": 0.0},
            )
            far = self.read_one_event()
            self.assertEqual(far["keys"], ["D"])
            self.assertIn("D", self.keyboard.held)

            post(
                self.url("/mock"),
                {"tracking": True, "nose": {"x": 0.17, "y": 0.0}, "mouth": 0.0, "wink": 0.0},
            )
            released = self.read_one_event()
            self.assertEqual(released["keys"], [])
            self.assertTrue(released["centered"])
            self.assertEqual(self.keyboard.held, set())
        finally:
            post(self.url("/deadzone-mode"), {"mode": "fixed"})
            self.hub.session.disarm()
            self.keyboard.reset()

    def test_site_calibrate_is_the_same_session_as_injected_keys(self) -> None:
        """POST /calibrate recentres the tracker that InputSession injects."""

        self.hub.session.arm()
        try:
            self.reset_center()
            post(
                self.url("/mock"),
                {"tracking": True, "nose": {"x": 0.12, "y": 0.0}, "mouth": 0.0, "wink": 0.0},
            )
            state = self.read_one_event()
            self.assertEqual(state["keys"], ["D"])
            self.assertIn("D", self.keyboard.held)

            post(self.url("/calibrate"))
            state = self.read_one_event()
            self.assertEqual(state["keys"], [])
            self.assertTrue(state["centered"])
            self.assertEqual(self.keyboard.held, set())
        finally:
            self.hub.session.disarm()
            self.keyboard.reset()

    def test_mock_endpoint_updates_the_streamed_state(self) -> None:
        self.reset_center()
        status, _ = post(
            self.url("/mock"),
            {"tracking": True, "nose": {"x": 0.12, "y": -0.12}, "mouth": 0.0, "wink": 0.0},
        )
        self.assertEqual(status, 200)
        state = self.read_one_event()
        self.assertEqual(state["direction"], "NE")
        self.assertEqual(state["keys"], ["W", "D"])

    def test_event_stream_emits_the_documented_contract(self) -> None:
        self.reset_center()
        state = self.read_one_event()
        self.assertLessEqual(
            {"centered", "nose", "direction", "keys", "mouth", "wink", "tracking"},
            set(state),
        )

    def test_event_stream_carries_match_status(self) -> None:
        """The second monitor needs to show arm state and who owns the keyboard."""

        state = self.read_one_event()
        self.assertLessEqual(
            {"armed", "held_keys", "shot_seconds", "frontmost", "game_focus"}, set(state)
        )

    def test_input_starts_disarmed(self) -> None:
        self.assertFalse(self.read_one_event()["armed"])
        self.assertEqual(self.keyboard.held, set())

    def test_disarm_endpoint_reports_disarmed(self) -> None:
        status, body = post(self.url("/disarm"))
        self.assertEqual(status, 200)
        self.assertFalse(body["armed"])

    def test_untrusted_origin_gets_no_cors_grant(self) -> None:
        """A random page must not be able to read the webcam or arm input."""

        request = urllib.request.Request(
            self.url("/config"), headers={"Origin": "https://evil.example"}
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

    def test_dev_server_origin_is_allowed(self) -> None:
        request = urllib.request.Request(
            self.url("/config"), headers={"Origin": "http://localhost:5173"}
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertEqual(
                response.headers.get("Access-Control-Allow-Origin"),
                "http://localhost:5173",
            )

    def test_served_ui_origin_can_read_the_camera_stream(self) -> None:
        """Original CameraFrame always fetched http://127.0.0.1:8765/stream.mjpg."""

        request = urllib.request.Request(
            self.url("/config"), headers={"Origin": "http://127.0.0.1:8765"}
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertEqual(
                response.headers.get("Access-Control-Allow-Origin"),
                "http://127.0.0.1:8765",
            )

    def test_requests_without_an_origin_still_work(self) -> None:
        """curl and the browser's own page send no Origin header."""

        with urllib.request.urlopen(self.url("/config"), timeout=5) as response:
            self.assertEqual(response.status, 200)

    def test_config_reports_whether_keyboard_output_can_work(self) -> None:
        with urllib.request.urlopen(self.url("/config"), timeout=5) as response:
            config = json.loads(response.read())
        self.assertIn("keyboard_problem", config)

    def test_mouth_trigger_reaches_the_event_stream(self) -> None:
        self.reset_center()
        post(self.url("/mock"), {"tracking": True, "nose": {"x": 0.0, "y": 0.0}, "mouth": 0.3, "wink": 0.0})
        state = self.read_one_event()
        self.assertTrue(state["mouth"]["active"])

    def reset_center(self) -> None:
        """Pin the neutral center to a known point so offsets are predictable.

        Tests share one server, and /calibrate clears the center, so a test that
        asserts on direction must re-establish the center it expects.
        """

        post(self.url("/mock"), {"tracking": True, "nose": {"x": 0.0, "y": 0.0}, "mouth": 0.0, "wink": 0.0})
        post(self.url("/calibrate"))
        self.read_one_event()

    def read_one_event(self, settle: int = 4) -> dict[str, object]:
        """Return a state produced after the most recent POST.

        The hub keeps only the latest state, so the first event on a new
        connection can predate the POST under test. Reading a few events lets
        the change propagate.
        """

        latest: dict[str, object] | None = None
        with urllib.request.urlopen(self.url("/events"), timeout=5) as stream:
            while settle > 0:
                line = stream.readline().decode("utf-8").strip()
                if line.startswith("data:"):
                    latest = json.loads(line[5:])
                    settle -= 1
        if latest is None:
            self.fail("no event received from the stream")
        return latest


    def test_built_orientation_ui_is_served_when_present(self) -> None:
        from bridge.server import UI_DIST

        if not (UI_DIST / "index.html").is_file():
            self.skipTest("onboarding/dist is not built")
        with urllib.request.urlopen(self.url("/"), timeout=5) as response:
            html = response.read().decode("utf-8")
        self.assertIn("<div id=\"root\">", html)
        self.assertIn("FIFA4ALL", html)


class OrientationLaunchTests(unittest.TestCase):
    def test_intro_url_is_localhost_root(self) -> None:
        from bridge.server import orientation_ui_url

        self.assertEqual(orientation_ui_url(), "http://127.0.0.1:8765/")
        self.assertEqual(orientation_ui_url(9000), "http://127.0.0.1:9000/")

    def test_preview_opens_default_browser_to_intro(self) -> None:
        from unittest.mock import patch

        from bridge.server import maybe_open_orientation_ui

        with patch("bridge.server.macos_open_bin", return_value=None):
            with patch("bridge.server.webbrowser.open", return_value=True) as opened:
                self.assertTrue(maybe_open_orientation_ui(preview=True, port=8765))
        opened.assert_called_once_with("http://127.0.0.1:8765/", new=1, autoraise=True)

    def test_macos_preview_uses_usr_bin_open(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import patch

        from bridge.server import maybe_open_orientation_ui

        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch("bridge.server.macos_open_bin", return_value="/usr/bin/open"):
            with patch("bridge.server.subprocess.run", return_value=completed) as run:
                with patch("bridge.server.webbrowser.open") as webbrowser_open:
                    self.assertTrue(maybe_open_orientation_ui(preview=True, port=8765))
        run.assert_called_once()
        self.assertEqual(
            run.call_args[0][0],
            ["/usr/bin/open", "http://127.0.0.1:8765/"],
        )
        webbrowser_open.assert_not_called()

    def test_macos_open_failure_prints_clickable_url(self) -> None:
        import io
        from types import SimpleNamespace
        from unittest.mock import patch

        from bridge.server import maybe_open_orientation_ui

        completed = SimpleNamespace(
            returncode=1, stdout="", stderr="LSOpenURLsWithRole() failed"
        )
        buf = io.StringIO()
        with patch("bridge.server.macos_open_bin", return_value="/usr/bin/open"):
            with patch("bridge.server.subprocess.run", return_value=completed):
                with patch("bridge.server.webbrowser.open", return_value=False):
                    with patch("sys.stdout", buf):
                        self.assertFalse(
                            maybe_open_orientation_ui(preview=True, port=8765)
                        )
        logged = buf.getvalue()
        self.assertIn("Could not open the orientation UI automatically", logged)
        self.assertIn("http://127.0.0.1:8765/", logged)
        self.assertIn("Open http://127.0.0.1:8765/ in your browser", logged)

    def test_no_preview_does_not_open_browser(self) -> None:
        from unittest.mock import patch

        from bridge.server import maybe_open_orientation_ui

        with patch("bridge.server.macos_open_bin", return_value="/usr/bin/open"):
            with patch("bridge.server.subprocess.run") as run:
                with patch("bridge.server.webbrowser.open") as opened:
                    self.assertFalse(maybe_open_orientation_ui(preview=False, port=8765))
        opened.assert_not_called()
        run.assert_not_called()

    def test_run_product_preview_opens_browser_without_webcam(self) -> None:
        from unittest.mock import patch

        from bridge.server import ControlHub, run_product

        with patch("bridge.server.macos_open_bin", return_value=None):
            with patch("bridge.server.webbrowser.open", return_value=True) as opened:
                with patch.object(ControlHub, "run", return_value=None):
                    with patch("bridge.server._build_overlay", return_value=None):
                        code = run_product(preview=True, mock=True, port=0, armed=False)
        self.assertEqual(code, 0)
        opened.assert_called_once()
        url = opened.call_args[0][0]
        self.assertTrue(url.startswith("http://127.0.0.1:"))
        self.assertTrue(url.endswith("/"))

    def test_run_product_preview_waits_then_uses_macos_open(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import patch

        from bridge.server import ControlHub, run_product

        order: list[str] = []
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")

        def wait(port: int, timeout: float = 5.0) -> bool:
            order.append("wait")
            return True

        def run_open(*_args: object, **_kwargs: object) -> SimpleNamespace:
            order.append("open")
            return completed

        with patch("bridge.server.wait_until_serving", side_effect=wait):
            with patch("bridge.server.macos_open_bin", return_value="/usr/bin/open"):
                with patch("bridge.server.subprocess.run", side_effect=run_open) as run:
                    with patch("bridge.server.webbrowser.open") as webbrowser_open:
                        with patch.object(ControlHub, "run", return_value=None):
                            with patch("bridge.server._build_overlay", return_value=None):
                                code = run_product(
                                    preview=True, mock=True, port=0, armed=False
                                )
        self.assertEqual(code, 0)
        self.assertEqual(order, ["wait", "open"])
        webbrowser_open.assert_not_called()
        argv = run.call_args[0][0]
        self.assertEqual(argv[0], "/usr/bin/open")
        self.assertTrue(argv[1].startswith("http://127.0.0.1:"))
        self.assertTrue(argv[1].endswith("/"))

    def test_run_product_no_preview_serves_ui_without_opening_browser(self) -> None:
        from unittest.mock import patch

        from bridge.server import ControlHub, run_product

        with patch("bridge.server.macos_open_bin", return_value="/usr/bin/open"):
            with patch("bridge.server.subprocess.run") as run:
                with patch("bridge.server.webbrowser.open") as opened:
                    with patch.object(ControlHub, "run", return_value=None):
                        code = run_product(preview=False, mock=True, port=0, armed=False)
        self.assertEqual(code, 0)
        opened.assert_not_called()
        run.assert_not_called()

    def test_preview_opens_website_and_keeps_overlay_separate(self) -> None:
        """Browser gets the site; overlay is a different native callback."""

        from unittest.mock import patch

        from bridge.server import ControlHub, run_product

        with patch("bridge.server.macos_open_bin", return_value=None):
            with patch("bridge.server.webbrowser.open", return_value=True) as opened:
                with patch.object(ControlHub, "run", return_value=None) as hub_run:
                    with patch(
                        "bridge.server._build_overlay", return_value="overlay-cb"
                    ) as build:
                        code = run_product(preview=True, mock=True, port=0, armed=False)
        self.assertEqual(code, 0)
        opened.assert_called_once()
        build.assert_called_once()
        hub_run.assert_called_once_with(on_frame="overlay-cb")

    def test_run_product_logs_url_when_ui_never_listens(self) -> None:
        import io
        from unittest.mock import patch

        from bridge.server import ControlHub, run_product

        buf = io.StringIO()
        with patch("bridge.server.wait_until_serving", return_value=False):
            with patch("bridge.server.macos_open_bin", return_value="/usr/bin/open"):
                with patch("bridge.server.subprocess.run") as run:
                    with patch("bridge.server.webbrowser.open") as opened:
                        with patch.object(ControlHub, "run", return_value=None):
                            with patch("bridge.server._build_overlay", return_value=None):
                                with patch("sys.stdout", buf):
                                    code = run_product(
                                        preview=True, mock=True, port=0, armed=False
                                    )
        self.assertEqual(code, 0)
        run.assert_not_called()
        opened.assert_not_called()
        logged = buf.getvalue()
        self.assertIn("Could not confirm the orientation UI is listening", logged)
        self.assertIn("http://127.0.0.1:", logged)
        self.assertIn("Open ", logged)


class OverlayStaysSeparateTests(unittest.TestCase):
    def test_overlay_is_vision_hud_not_website_chrome(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        overlay = (root / "bridge" / "overlay_view.py").read_text(encoding="utf-8")
        live = (root / "onboarding" / "src" / "screens" / "Live.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("Reset center", live)
        self.assertIn("calibrate", live)
        for phrase in (
            '"Find your center"',
            '"Welcome"',
            '"Redo training"',
            '"WELCOME"',
            '"Training Camp"',
        ):
            self.assertNotIn(phrase, overlay)
        self.assertIn('"RESET"', overlay)
        self.assertIn('"FIXED"', overlay)
        self.assertIn('"FOLLOW"', overlay)
        self.assertIn('"NO FACE"', overlay)
        self.assertIn('"FIFA4ALL"', overlay)


class OverlayDeadzoneSwitchTests(unittest.TestCase):
    """FIXED / FOLLOW on the look-axis overlay drive the live injector."""

    def test_mode_buttons_sit_under_reset_and_do_not_overlap_it(self) -> None:
        from bridge.overlay_view import hit_mode_button, mode_button_rects, reset_button_rect

        width, height = 640, 360
        rx1, ry1, rx2, ry2 = reset_button_rect(width, height)
        rects = mode_button_rects(width, height)
        self.assertEqual(set(rects), {"fixed", "follow"})
        for mode, (x1, y1, x2, y2) in rects.items():
            with self.subTest(mode=mode):
                self.assertGreater(y1, ry2)
                self.assertLess(x1, x2)
                self.assertLess(y1, y2)
                self.assertGreaterEqual(x1, rx1)
                self.assertLessEqual(x2, rx2)
                self.assertIsNone(hit_mode_button((rx1 + rx2) // 2, (ry1 + ry2) // 2, width, height))
                self.assertEqual(hit_mode_button((x1 + x2) // 2, (y1 + y2) // 2, width, height), mode)

    def test_overlay_follow_click_changes_the_same_machine_as_injected_keys(self) -> None:
        from bridge.overlay_view import apply_overlay_click, mode_button_rects
        from bridge.source import MockSource
        from output.keyboard import RecordingKeyboard
        from output.session import InputSession

        source = MockSource()
        source.machine.calibrate((0.5, 0.5))
        keyboard = RecordingKeyboard()
        session = InputSession(keyboard, armed=True)
        self.assertEqual(source.machine.deadzone_mode, "fixed")

        fx1, fy1, fx2, fy2 = mode_button_rects(640, 360)["follow"]
        self.assertEqual(
            apply_overlay_click(source, (fx1 + fx2) // 2, (fy1 + fy2) // 2, 640, 360),
            "follow",
        )
        self.assertEqual(source.machine.deadzone_mode, "follow")

        far = source.machine.update(
            nose=(0.70, 0.50), features={}, tracking_valid=True
        )
        session.apply(far)
        self.assertEqual(far["keys"], ["D"])
        self.assertIn("D", keyboard.held)

        released = source.machine.update(
            nose=(0.67, 0.50), features={}, tracking_valid=True
        )
        session.apply(released)
        self.assertEqual(released["keys"], [])
        self.assertTrue(released["centered"])
        self.assertEqual(keyboard.held, set())

        xx1, xy1, xx2, xy2 = mode_button_rects(640, 360)["fixed"]
        self.assertEqual(
            apply_overlay_click(source, (xx1 + xx2) // 2, (xy1 + xy2) // 2, 640, 360),
            "fixed",
        )
        self.assertEqual(source.machine.deadzone_mode, "fixed")

    def test_live_overlay_callback_wires_mode_clicks_to_the_machine(self) -> None:
        from pathlib import Path

        server = (Path(__file__).resolve().parent.parent / "bridge" / "server.py").read_text(
            encoding="utf-8"
        )
        overlay = (
            Path(__file__).resolve().parent.parent / "tracking" / "overlay.py"
        ).read_text(encoding="utf-8")
        self.assertIn("apply_overlay_click", server)
        self.assertIn("poll_mode_click", server)
        self.assertIn("set_deadzone_mode", server)
        self.assertIn("poll_mode_click", overlay)
        self.assertIn('"Fixed"', overlay)
        self.assertIn('"Follow"', overlay)

    def test_overlay_reset_click_still_calibrates(self) -> None:
        from bridge.overlay_view import apply_overlay_click, reset_button_rect
        from bridge.source import MockSource

        source = MockSource()
        source.machine.calibrate((0.5, 0.5))
        x1, y1, x2, y2 = reset_button_rect(640, 360)
        self.assertEqual(
            apply_overlay_click(source, (x1 + x2) // 2, (y1 + y2) // 2, 640, 360),
            "reset",
        )
        self.assertIsNone(source.machine.center)


class OrientationCameraFeedTests(unittest.TestCase):
    """The first website push showed MJPEG in CameraFrame during calibration."""

    def test_webcam_source_tells_the_ui_it_has_video(self) -> None:
        from bridge.server import build_server
        from bridge.source import WebcamSource

        source = WebcamSource()
        server, _hub = build_server(source, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/config", timeout=5) as response:
                self.assertTrue(json.loads(response.read())["has_video"])
        finally:
            server.shutdown()
            server.server_close()

    def test_mjpeg_endpoint_publishes_jpeg_bytes(self) -> None:
        from bridge.server import build_server
        from bridge.source import ControlSource

        jpeg = b"\xff\xd8\xff\xd9"

        class JpegSource(ControlSource):
            def frames(self):
                while True:
                    sleep(0.01)
                    yield ({"tracking": True, "centered": True}, jpeg)

        source = JpegSource()
        server, hub = build_server(source, port=0)
        hub.start()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/stream.mjpg", timeout=5
            ) as response:
                self.assertIn("multipart/x-mixed-replace", response.headers.get("Content-Type", ""))
                blob = response.read(256)
            self.assertIn(jpeg, blob)
            self.assertIn(b"Content-Type: image/jpeg", blob)
        finally:
            hub.stop()
            server.shutdown()
            server.server_close()

    def test_camera_frame_still_uses_the_original_mjpeg_path(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        frame = (root / "onboarding" / "src" / "components" / "CameraFrame.tsx").read_text(
            encoding="utf-8"
        )
        center = (root / "onboarding" / "src" / "screens" / "Center.tsx").read_text(
            encoding="utf-8"
        )
        source = (root / "onboarding" / "src" / "control" / "source.ts").read_text(
            encoding="utf-8"
        )
        self.assertIn('${BRIDGE_URL}/stream.mjpg', frame)
        self.assertIn("src={`${BRIDGE_URL}/stream.mjpg`}", frame)
        self.assertIn("hasVideo={config.has_video}", center)
        self.assertIn('"http://127.0.0.1:8765"', source)
        self.assertNotIn("navigator.mediaDevices", frame)
        self.assertNotIn("getUserMedia(", frame)

    def test_reticle_spans_the_frame_so_it_cannot_cover_the_feed(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        reticle = (root / "onboarding" / "src" / "components" / "Reticle.tsx").read_text(
            encoding="utf-8"
        )
        css = (root / "onboarding" / "src" / "components" / "Reticle.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("viewBox={`0 0 ${width} ${height}`}", reticle)
        self.assertIn(".reticle * {\n  vector-effect: non-scaling-stroke;\n}", css)
        self.assertNotIn("width: 0;\n  height: 0;", css)


class WebcamCalibrateTests(unittest.TestCase):
    def test_site_reset_recentres_the_same_machine_without_opening_a_camera(self) -> None:
        from bridge.source import WebcamSource

        source = WebcamSource()
        source.machine.calibrate((0.5, 0.5))
        off = (0.70, 0.50)
        before = source.machine.update(nose=off, features={}, tracking_valid=True)
        self.assertFalse(before["centered"])
        self.assertEqual(before["keys"], ["D"])

        # POST /calibrate and overlay RESET both call source.calibrate().
        source.calibrate()
        self.assertTrue(
            source.apply_pending_calibrate(
                off,
                {
                    "mouth_opening": 0.04,
                    "left_eye_opening": 0.08,
                    "right_eye_opening": 0.08,
                    "eyebrow_raise": 0.10,
                },
            )
        )
        after = source.machine.update(nose=off, features={}, tracking_valid=True)
        self.assertTrue(after["centered"])
        self.assertEqual(after["keys"], [])
        self.assertEqual(source.machine.mouth_rest, 0.04)
        self.assertEqual(source.machine.eye_rest, 0.08)
        self.assertEqual(source.machine.brow_rest, 0.10)

    def test_a_second_site_reset_still_drives_the_same_injector(self) -> None:
        """Website RESET stays live after the first calibrate; same machine."""

        from bridge.source import WebcamSource

        source = WebcamSource()
        source.machine.calibrate((0.5, 0.5))
        first = (0.70, 0.50)
        source.calibrate()
        source.apply_pending_calibrate(
            first,
            {"mouth_opening": 0.04, "left_eye_opening": 0.08, "right_eye_opening": 0.08},
        )
        self.assertEqual(
            source.machine.update(nose=first, features={}, tracking_valid=True)["keys"],
            [],
        )

        second = (0.30, 0.50)
        moved = source.machine.update(nose=second, features={}, tracking_valid=True)
        self.assertEqual(moved["keys"], ["A"])

        source.calibrate()
        source.apply_pending_calibrate(
            second,
            {"mouth_opening": 0.05, "left_eye_opening": 0.08, "right_eye_opening": 0.08},
        )
        after = source.machine.update(nose=second, features={}, tracking_valid=True)
        self.assertTrue(after["centered"])
        self.assertEqual(after["keys"], [])
        self.assertEqual(source.machine.mouth_rest, 0.05)


if __name__ == "__main__":
    unittest.main()
