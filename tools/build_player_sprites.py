"""Process raw frames into app-ready sprites and install them.

Generation runs kit by kit, so this has to cope with a half-finished cast: any
pose a kit is still missing falls back to that kit's own idle frame, and a kit
with no frames at all falls back to a completed kit. That keeps every screen
rendering a real player instead of a broken image while the rest generates.
"""
from __future__ import annotations

import json
import os
import sys

from PIL import Image

ALPHA_FLOOR = 16
# Rendered height of a standing player. The largest a player is drawn on screen
# is 300px, so 600 is exactly retina-sharp; the raw 1024x1536 frames are three
# times more than any display needs and cost 15MB across the cast.
IDLE_HEIGHT = 600
POSES = ["idle", "run", "runb", "shoot", "pass", "celebrate", "back", "backrun", "backrunb"]
KITS = ["teal", "crimson", "lime", "amber", "slate", "purple"]
# A missing pose reuses this frame from the same kit. Chains resolve, so a kit
# with no rear run frames degrades backrunb -> backrun -> back -> idle.
FALLBACK = {"runb": "run", "back": "idle", "shoot": "idle", "pass": "idle",
            "celebrate": "idle", "run": "idle",
            "backrun": "back", "backrunb": "backrun"}


def tight(path: str) -> Image.Image:
    im = Image.open(path).convert("RGBA")
    im.putalpha(im.getchannel("A").point(lambda p: p if p > ALPHA_FLOOR else 0))
    box = im.getbbox()
    if box is None:
        raise ValueError(f"{path} is fully transparent")
    return im.crop(box)


def build(src_root: str, out: str) -> dict:
    os.makedirs(out, exist_ok=True)
    have = {k: os.path.exists(f"{src_root}/{k}/_idle_raw.png") for k in KITS}
    donor = next(k for k in KITS if have[k])
    manifest, report = {}, []

    for kit in KITS:
        src_kit = kit if have[kit] else donor
        if not have[kit]:
            report.append(f"{kit}: NO FRAMES YET -> borrowing {donor}")
        scale = IDLE_HEIGHT / tight(f"{src_root}/{src_kit}/_idle_raw.png").height
        sizes = {}
        for pose in POSES:
            path = f"{src_root}/{src_kit}/_{pose}_raw.png"
            used = pose
            while not os.path.exists(path) and used in FALLBACK:
                used = FALLBACK[used]
                path = f"{src_root}/{src_kit}/_{used}_raw.png"
            if not os.path.exists(path):
                continue
            if used != pose:
                report.append(f"{kit}/{pose}: missing -> using {used}")
            im = tight(path)
            im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
            im.save(f"{out}/{kit}-{pose}.png")
            sizes[pose] = im.size
        manifest[kit] = sizes
    json.dump(manifest, open(f"{out}/sprites.json", "w"), indent=2, sort_keys=True)
    return {"manifest": manifest, "report": report}


if __name__ == "__main__":
    res = build(sys.argv[1], sys.argv[2])
    for line in res["report"]:
        print(" ", line)
    complete = [k for k, v in res["manifest"].items() if len(v) == len(POSES)]
    print(f"installed {len(res['manifest'])} kits, {len(complete)} with a full pose set")
