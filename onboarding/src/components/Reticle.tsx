/**
 * The nose-ball reticle: FIFA4ALL's signature motif.
 *
 * The ball sits on the user's actual nose in the camera image, and the zone
 * graphic is anchored at their calibrated neutral position. Both are supplied
 * in pixels by `CameraFrame`, which owns the mapping from normalized landmark
 * coordinates into the cropped video element.
 *
 * Geometry is drawn in "control space", where the y axis is pre-multiplied by
 * the threshold y_scale. Distance checks are a plain circle in that space, so
 * the SVG stays circular and a single non-uniform transform produces the
 * ellipse that is actually correct on screen. Zone sizes therefore come from
 * the thresholds the input logic uses, as TECHNICAL_SPEC.md requires.
 */

import type { ControlState, Direction, Thresholds } from "../types";
import { Ball } from "./Ball";
import "./Reticle.css";

const LABELS: ReadonlyArray<{ key: string; x: number; y: number }> = [
  { key: "W", x: 0, y: -1 },
  { key: "D", x: 1, y: 0 },
  { key: "S", x: 0, y: 1 },
  { key: "A", x: -1, y: 0 },
];

/** Pixels-per-normalized-unit for each axis, plus where neutral sits. */
export interface ReticleMapping {
  /** Size of the frame the overlay covers, in pixels. */
  readonly width: number;
  readonly height: number;
  readonly anchorX: number;
  readonly anchorY: number;
  readonly ballX: number;
  readonly ballY: number;
  /** Horizontal pixels per unit of control space. */
  readonly scaleX: number;
  /** Vertical pixels per unit of control space. */
  readonly scaleY: number;
}

interface ReticleProps {
  readonly state: ControlState;
  readonly thresholds: Thresholds;
  readonly mapping: ReticleMapping;
  readonly lockProgress?: number;
  readonly locked?: boolean;
  readonly showKeys?: boolean;
}

export function Reticle({
  state,
  thresholds,
  mapping,
  lockProgress = 0,
  locked = false,
  showKeys = true,
}: ReticleProps) {
  const { width, height, anchorX, anchorY, ballX, ballY, scaleX, scaleY } = mapping;
  const neutral = thresholds.exit_radius;
  const inner = thresholds.enter_radius;
  const outer = neutral * 2.9;
  const circumference = 2 * Math.PI * neutral;
  const moving = state.direction !== null;

  // Label offsets use each axis separately so they hug the real ellipse.
  const labelRadius = outer * 0.82;

  return (
    <>
      {/* The SVG spans the whole frame. A zero-sized viewport positioned at the
          anchor paints nothing, whatever overflow says, so the geometry is
          translated into place instead. */}
      <svg
        className={`reticle ${locked ? "is-locked" : ""}`}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
      >
        <g transform={`translate(${anchorX} ${anchorY}) scale(${scaleX} ${scaleY})`}>
          <circle className="reticle__radar" r={outer} />
          <circle className="reticle__radar" r={outer * 0.66} />
          <line className="reticle__cross" x1={-outer} y1={0} x2={outer} y2={0} />
          <line className="reticle__cross" x1={0} y1={-outer} x2={0} y2={outer} />

          {[45, 135, 225, 315].map((angle) => {
            const radians = (angle * Math.PI) / 180;
            return (
              <line
                key={angle}
                className="reticle__divider"
                x1={Math.cos(radians) * neutral}
                y1={Math.sin(radians) * neutral}
                x2={Math.cos(radians) * outer}
                y2={Math.sin(radians) * outer}
              />
            );
          })}

          <circle className="reticle__inner" r={inner} />
          <circle className={`reticle__neutral ${moving ? "is-active" : ""}`} r={neutral} />

          {lockProgress > 0 && (
            <circle
              className="reticle__lock"
              r={neutral}
              strokeDasharray={circumference}
              strokeDashoffset={circumference * (1 - lockProgress)}
              transform="rotate(-90)"
            />
          )}

          {state.direction !== null && (
            <path className="reticle__wedge" d={wedgePath(state.direction, neutral, outer)} />
          )}
        </g>
      </svg>

      {showKeys &&
        LABELS.map((label) => (
          <span
            key={label.key}
            className={`reticle__key ${
              (state.keys as readonly string[]).includes(label.key) ? "is-active" : ""
            }`}
            style={{
              left: anchorX + label.x * labelRadius * scaleX,
              top: anchorY + label.y * labelRadius * scaleY,
            }}
          >
            {label.key}
          </span>
        ))}

      <div className="reticle__ball" style={{ left: ballX, top: ballY }}>
        <Ball size={26} spin={moving} />
      </div>

      {!state.tracking && <div className="reticle__lost">TRACKING LOST</div>}
    </>
  );
}

/** Build a 45-degree wedge for the active direction zone, in control space. */
function wedgePath(direction: Direction, from: number, to: number): string {
  const centers: Record<Direction, number> = {
    E: 0, NE: -45, N: -90, NW: -135, W: 180, SW: 135, S: 90, SE: 45,
  };
  const mid = centers[direction];
  const start = ((mid - 22.5) * Math.PI) / 180;
  const end = ((mid + 22.5) * Math.PI) / 180;
  const point = (radius: number, angle: number) =>
    `${(Math.cos(angle) * radius).toFixed(4)} ${(Math.sin(angle) * radius).toFixed(4)}`;
  return [
    `M ${point(from, start)}`,
    `L ${point(to, start)}`,
    `A ${to} ${to} 0 0 1 ${point(to, end)}`,
    `L ${point(from, end)}`,
    `A ${from} ${from} 0 0 0 ${point(from, start)}`,
    "Z",
  ].join(" ");
}
