"""Prove that synthetic key events actually reach macOS.

`joe_plan.txt` records "synthetic keyboard events not reaching Luna" as a
blocker. Almost always the cause is mundane: without Accessibility permission
macOS discards injected events silently, with no error anywhere.

This posts a key and listens for it with an event tap. If the tap observes the
key, the event reached the system input stack, which is the same stack the
browser running Amazon Luna reads from.

Run it before a demo:

    .venv-mediapipe/bin/python -m output.selftest
"""

from __future__ import annotations

import sys

from output.keyboard import probe_key_output


def main() -> int:
    ok, message = probe_key_output()
    print(("PASS: " if ok else "FAIL: ") + message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
