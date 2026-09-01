#!/usr/bin/env python3
"""Tests for the computer-remote agent. Stdlib only: python3 -m unittest discover."""

from __future__ import annotations

import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import remote_agentd as agent  # noqa: E402

TOKEN = "test-token-0123456789abcdef"

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
)


class FakeBackend(agent.Backend):
    name = "fake"

    def __init__(self):
        self.calls: list[tuple] = []
        self.clipboard = "on the clipboard"

    def screen_size(self):
        return 1920, 1080

    def cursor_position(self):
        return 10, 20

    def screenshot(self, path, region):
        self.calls.append(("screenshot", region))
        with open(path, "wb") as handle:
            handle.write(PNG)

    def resize(self, path, max_width):
        self.calls.append(("resize", max_width))

    def move(self, x, y):
        self.calls.append(("move", x, y))

    def click(self, button, count):
        self.calls.append(("click", button, count))

    def mouse_down(self, button):
        self.calls.append(("down", button))

    def mouse_up(self, button):
        self.calls.append(("up", button))

    def scroll(self, dx, dy):
        self.calls.append(("scroll", dx, dy))

    def type_text(self, text):
        self.calls.append(("text", text))

    def key(self, combo):
        self.calls.append(("key", combo))

    def clipboard_get(self):
        return self.clipboard

    def clipboard_set(self, text):
        self.clipboard = text


class ParseTests(unittest.TestCase):
    def test_combo_splits_modifiers(self):
        self.assertEqual(agent.parse_combo("ctrl+shift+t"), (["ctrl", "shift"], "t"))

    def test_modifier_aliases_are_canonical(self):
        self.assertEqual(agent.parse_combo("cmd+s")[0], ["meta"])
        self.assertEqual(agent.parse_combo("command+s")[0], ["meta"])
        self.assertEqual(agent.parse_combo("control+c")[0], ["ctrl"])

    def test_key_aliases(self):
        self.assertEqual(agent.parse_combo("return")[1], "enter")
        self.assertEqual(agent.parse_combo("pgdn")[1], "pagedown")

    def test_literal_plus(self):
        self.assertEqual(agent.parse_combo("ctrl++"), (["ctrl"], "plus"))

    def test_unknown_modifier_rejected(self):
        with self.assertRaises(agent.AgentError):
            agent.parse_combo("hyper+x")

    def test_region_forms(self):
        self.assertEqual(agent.parse_region("10,20,30,40"), (10, 20, 30, 40))
        self.assertEqual(agent.parse_region([1, 2, 3, 4]), (1, 2, 3, 4))
        self.assertIsNone(agent.parse_region(None))
        for bad in ("1,2,3", [1, 2, 3, 0], ["a", "b", "c", "d"]):
            with self.assertRaises(agent.AgentError):
                agent.parse_region(bad)


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()

    def test_click_moves_first_when_given_coordinates(self):
        agent.perform(self.backend, {"type": "click", "x": 5, "y": 6, "count": 2})
        self.assertEqual(self.backend.calls, [("move", 5, 6), ("click", "left", 2)])

    def test_drag_presses_and_releases(self):
        agent.perform(
            self.backend, {"type": "drag", "x": 1, "y": 2, "to_x": 3, "to_y": 4}
        )
        self.assertEqual(
            self.backend.calls,
            [("move", 1, 2), ("down", "left"), ("move", 3, 4), ("up", "left")],
        )

    def test_key_accepts_string_or_list(self):
        agent.perform(self.backend, {"type": "key", "keys": "ctrl+s"})
        agent.perform(self.backend, {"type": "key", "keys": ["alt+tab", "enter"]})
        self.assertEqual(
            self.backend.calls, [("key", "ctrl+s"), ("key", "alt+tab"), ("key", "enter")]
        )

    def test_rejects_unknown_action(self):
        with self.assertRaises(agent.AgentError) as ctx:
            agent.perform(self.backend, {"type": "teleport"})
        self.assertEqual(ctx.exception.status, 400)

    def test_rejects_bad_button_and_count(self):
        for action in ({"type": "click", "button": "thumb"}, {"type": "click", "count": 99}):
            with self.assertRaises(agent.AgentError):
                agent.perform(self.backend, action)

    def test_sleep_is_bounded(self):
        with self.assertRaises(agent.AgentError):
            agent.perform(self.backend, {"type": "sleep", "ms": 999999})


class ServerTestCase(unittest.TestCase):
    read_only = False

    def setUp(self):
        self.backend = FakeBackend()
        agent.Handler.backend = self.backend
        agent.Handler.token = TOKEN
        agent.Handler.allow_input = not self.read_only
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), agent.Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def call(self, path, payload=None, method="POST", token=TOKEN):
        body = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(self.url + path, data=body, method=method)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.read(), response.headers.get("Content-Type")


class ServerTests(ServerTestCase):
    def test_health_reports_backend(self):
        _, body, _ = self.call("/health", method="GET")
        data = json.loads(body)
        self.assertEqual(data["backend"], "fake")
        self.assertEqual(data["screen"], {"width": 1920, "height": 1080})
        self.assertFalse(data["read_only"])

    def test_missing_token_is_401(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.call("/health", method="GET", token=None)
        self.assertEqual(ctx.exception.code, 401)

    def test_wrong_token_is_401(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.call("/health", method="GET", token="nope")
        self.assertEqual(ctx.exception.code, 401)

    def test_screenshot_returns_png_bytes(self):
        status, body, ctype = self.call("/screenshot", {"scale": 800})
        self.assertEqual(status, 200)
        self.assertEqual(ctype, "image/png")
        self.assertEqual(body, PNG)
        self.assertIn(("resize", 800), self.backend.calls)

    def test_screenshot_passes_region(self):
        self.call("/screenshot", {"region": [1, 2, 3, 4]})
        self.assertIn(("screenshot", (1, 2, 3, 4)), self.backend.calls)

    def test_input_runs_actions_in_order(self):
        status, body, _ = self.call(
            "/input",
            {"actions": [{"type": "move", "x": 1, "y": 2}, {"type": "text", "text": "hi"}]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["performed"], 2)
        self.assertEqual(self.backend.calls, [("move", 1, 2), ("text", "hi")])

    def test_input_rejects_empty_and_oversized_batches(self):
        for payload in ({"actions": []}, {"actions": [{"type": "move", "x": 0, "y": 0}] * 65}):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.call("/input", payload)
            self.assertEqual(ctx.exception.code, 400)

    def test_clipboard_round_trip(self):
        _, body, _ = self.call("/clipboard", method="GET")
        self.assertEqual(json.loads(body)["text"], "on the clipboard")
        self.call("/clipboard", {"text": "written"})
        self.assertEqual(self.backend.clipboard, "written")

    def test_unknown_route_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.call("/nope", {})
        self.assertEqual(ctx.exception.code, 404)

    def test_invalid_json_is_400(self):
        req = urllib.request.Request(self.url + "/input", data=b"{oops", method="POST")
        req.add_header("Authorization", f"Bearer {TOKEN}")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 400)


class ReadOnlyServerTests(ServerTestCase):
    read_only = True

    def test_screenshots_still_work(self):
        status, _, _ = self.call("/screenshot", {})
        self.assertEqual(status, 200)

    def test_input_is_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.call("/input", {"actions": [{"type": "move", "x": 1, "y": 1}]})
        self.assertEqual(ctx.exception.code, 403)

    def test_clipboard_write_is_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.call("/clipboard", {"text": "nope"})
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
