"""Tests for the orientation bridge server and its control sources."""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from bridge.server import build_server
from bridge.source import MockSource
from output.keyboard import RecordingKeyboard
from output.session import InputSession


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
        self.assertEqual(
            set(state), {"centered", "nose", "direction", "keys", "mouth", "wink", "tracking"}
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


if __name__ == "__main__":
    unittest.main()
