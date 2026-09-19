# macOS + Google Chrome + Amazon Luna setup

Target (locked): **EA Sports FC via Amazon Luna in Google Chrome on a Mac, default US keyboard.**

This repository was developed on a **Linux cloud VM**. It **cannot** open Amazon Luna, grant Accessibility, or confirm that synthetic keys reach EA FC. Follow this on the Mac. Do not treat CI/pytest success as Luna verification.

## 1. Accessibility permission (required for Quartz HID keys)

OS-level `CGEventPost` keyboard events are blocked unless the launching app is trusted.

1. Open **System Settings**.
2. Open **Privacy & Security**.
3. Open **Accessibility**.
4. Unlock with password / Touch ID if the lock is closed.
5. Enable the app that will spawn Python:
   - **Terminal** if you run `python -m fifa4all` from Terminal.app
   - **iTerm** / **Ghostty** / **VS Code** / **Cursor** if you launch from those
   - If a **Python** binary appears in the list, enable that too
6. Still under **Privacy & Security**, open **Input Monitoring**.
7. Enable the same app if macOS shows it (newer macOS versions sometimes require both).
8. **Fully quit** FIFA4ALL (and often the terminal app) and start it again. Permission changes do not apply to an already-running process.

If keys do nothing, this list is the first thing to re-check. Safari/Firefox are not the target browser.

## 2. Chrome must be the frontmost app

Quartz HID events go to the **focused application**, not to “whatever tab once loaded Luna.”

1. Open **Google Chrome** (not Safari, not Arc, not Firefox).
2. Sign in to [Amazon Luna](https://luna.amazon.com/) and launch **EA Sports FC**.
3. Click the **Luna game view** so Chrome is frontmost and the game canvas is focused.
4. Start FIFA4ALL in a terminal.
5. During the **ready delay** (default 5 seconds on Mac live injectors), click Chrome again.
6. Prefer `python -m fifa4all --no-preview` while playing. An OpenCV preview window often becomes key and then WASD types into the overlay instead of Luna.
7. Do not click the terminal back to the foreground while a key is meant to stay held.

## 3. Suggested first-run order

Manual keys are already known: WASD move, Space shoots, L passes. Hold duration on Space/L changes shot/pass strength.

1. In a text editor, run `python -m fifa4all --key-smoke --injector dry-run` and confirm the printed `KEY down` / `KEY up` sequence.
2. Click TextEdit (or similar), run `python -m fifa4all --key-smoke` on the Mac, and confirm real characters / spaces appear with holds (this only proves OS injection, not Luna).
3. Click the Chrome Luna window, run the same `--key-smoke` again, and watch whether the footballer moves / shoots / passes. **This step is still unverified.**
4. Only then run the live camera path.

## 4. Live camera command

```bash
source .venv/bin/activate
python -m fifa4all --no-preview --calibrate-seconds 2 --ready-delay 5
```

Hold a still, closed-mouth, both-eyes-open face during calibration. Then click Chrome.

## 5. What this VM could not do

- Grant Accessibility
- Open Google Chrome / Amazon Luna / EA FC
- Measure end-to-end latency into the game
- Confirm that Luna accepts `CGEvent` HID key downs (some cloud-gaming clients ignore synthetic input)

If Luna ignores synthetic keys, fallbacks (hardware HID dongle, another OS) are future work — not this MVP.
