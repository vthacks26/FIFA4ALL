"""Practice-calibration direction colors on the website reticle."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

RETICLE_CSS = (
    Path(__file__).resolve().parent.parent / "onboarding" / "src" / "components" / "Reticle.css"
)


def _rule(css: str, selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]+)\}", css)
    if match is None:
        raise AssertionError(f"missing CSS rule {selector}")
    return match.group(1)


class PracticeDirectionColorTests(unittest.TestCase):
    def test_looked_at_direction_is_green_others_are_gray(self) -> None:
        css = RETICLE_CSS.read_text(encoding="utf-8")

        idle_wedge = _rule(css, ".reticle__wedge")
        active_wedge = _rule(css, ".reticle__wedge.is-active")
        idle_key = _rule(css, ".reticle__key")
        active_key = _rule(css, ".reticle__key.is-active")

        self.assertIn("142, 163, 192", idle_wedge)
        self.assertNotIn("var(--lime)", idle_wedge)
        self.assertIn("var(--lime)", active_wedge)

        self.assertIn("var(--navy-700)", idle_key)
        self.assertIn("var(--muted)", idle_key)
        self.assertIn("var(--lime)", active_key)
        self.assertNotIn("var(--navy-700)", active_key)
