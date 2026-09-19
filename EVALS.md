# Evals

## Automated (Linux, this PR)

Run: `python -m pytest tests/`

| Check | Expected |
| --- | --- |
| Dead zone | Small yaw/pitch → no WASD |
| Cardinal + diagonal holds | Threshold crossings hold W/A/S/D including W+A / W+D |
| Neutral | Return to dead zone releases movement keys |
| Mouth hold duration | Space down for the open-mouth interval, then up |
| Wink hold duration | L down while one eye closed |
| Blink | Both eyes closed → no L |
| Face lost | All keys released |
| Injector | Unknown keys rejected; Quartz refused on non-Darwin |
| Replay CLI | `tests/fixtures/replay_mixed.json` emits down/up events |

## Remaining Luna-on-Mac (manual)

Not executed here.

1. Accessibility + Input Monitoring enabled for the launching app; process restarted.
2. `--key-smoke` while TextEdit is focused produces W/A/S/D/space/L with visible hold gaps.
3. Chrome frontmost, Luna FC running, `--key-smoke` moves the player, Space shoots with charge, L passes with charge.
4. Live `--no-preview` session: head tilts hold WASD; mouth hold charges shot; wink hold passes; blink does not pass; looking away releases keys; no stuck keys after quit.
5. Confirm OpenCV preview, if used, does not steal Chrome focus.

Until steps 3–4 pass, do not call the FIFA demo verified.
