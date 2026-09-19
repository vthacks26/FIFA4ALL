"""Cut the supplied low-poly reference renders into per-character sprites.

Colour distance from the background cannot separate the figures: pale skin and
white kit sit close to the lavender ground and get punched out. Instead, flood
fill inward from the border. Anything the fill cannot reach is the character,
whatever colour it happens to be, and the fill walks the soft cast shadow
gradient so the shadow disappears with it.
"""

import os
import sys

import cv2
import numpy as np


def extract(src: str, out_dir: str, tag: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    image = cv2.imread(src, cv2.IMREAD_COLOR)
    height, width = image.shape[:2]

    background = _background_mask(image)
    figure = (~background).astype(np.uint8)
    figure = cv2.morphologyEx(figure, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    figure = _fill_holes(figure)
    figure = (figure & ~_shadow_mask(image)).astype(np.uint8)

    # Segment on the upper band: the figures stand apart there even when their
    # feet nearly touch.
    columns = figure[: int(height * 0.70), :].sum(axis=0)
    runs, start = [], None
    for x in range(width):
        if columns[x] > 6 and start is None:
            start = x
        elif columns[x] <= 6 and start is not None:
            if x - start > 40:
                runs.append((start, x))
            start = None
    if start is not None and width - start > 40:
        runs.append((start, width))

    print(f"{tag}: {len(runs)} figures")
    for index, (x0, x1) in enumerate(runs, start=1):
        rows = np.where(figure[:, x0:x1].sum(axis=1) > 3)[0]
        if len(rows) == 0:
            continue
        pad = 4
        y0, y1 = max(0, rows[0] - pad), min(height, rows[-1] + 1 + pad)
        x0p, x1p = max(0, x0 - pad), min(width, x1 + pad)

        crop = image[y0:y1, x0p:x1p]
        mask = figure[y0:y1, x0p:x1p]
        # Keep only the largest blob so a neighbour's stray pixels do not ride along.
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        if count > 1:
            largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            mask = (labels == largest).astype(np.uint8)

        alpha = cv2.GaussianBlur(mask * 255, (3, 3), 0)
        rgba = np.dstack([crop, alpha])
        path = os.path.join(out_dir, f"{tag}-{index}.png")
        cv2.imwrite(path, rgba)
        print(f"  {tag}-{index}.png {x1p - x0p}x{y1 - y0}")


def _background_mask(image: np.ndarray) -> np.ndarray:
    """Flood fill inward from every border pixel."""

    height, width = image.shape[:2]
    filled = np.zeros((height + 2, width + 2), np.uint8)
    # Tolerance compares against the neighbour, not the seed, so the fill walks
    # the shadow's gradient without leaking across a figure's hard edge.
    # Tight: a looser fill walks through anti-aliased edges into white kit
    # panels and eats them. The shadow is removed separately instead.
    tolerance = (8, 8, 8)
    work = image.copy()
    for seed in _border_seeds(width, height):
        if filled[seed[1] + 1, seed[0] + 1]:
            continue
        cv2.floodFill(work, filled, seed, 0, tolerance, tolerance, 4 | (255 << 8))
    return filled[1:-1, 1:-1].astype(bool)


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """Close regions the fill ate into, such as a white stripe on a jersey."""

    height, width = mask.shape
    flood = np.zeros((height + 2, width + 2), np.uint8)
    inverted = (1 - mask).astype(np.uint8) * 255
    cv2.floodFill(inverted, flood, (0, 0), 0)
    # Anything still set in `inverted` was a hole enclosed by the figure.
    return ((mask > 0) | (inverted > 0)).astype(np.uint8)


def _shadow_mask(image: np.ndarray) -> np.ndarray:
    """The baked cast shadow: near-neutral, light, and low on the frame."""

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation, value = hsv[:, :, 1], hsv[:, :, 2]
    band = np.zeros(saturation.shape, dtype=bool)
    # Reaches up to mid-thigh: the ground shadow shows between the legs, and
    # hole filling would otherwise re-admit it as figure.
    band[int(saturation.shape[0] * 0.55) :, :] = True
    return band & (saturation < 55) & (value > 185)


def _border_seeds(width: int, height: int):
    step = 8
    for x in range(0, width, step):
        yield (x, 0)
        yield (x, height - 1)
    for y in range(0, height, step):
        yield (0, y)
        yield (width - 1, y)


if __name__ == "__main__":
    extract(sys.argv[1], sys.argv[2], sys.argv[3])
