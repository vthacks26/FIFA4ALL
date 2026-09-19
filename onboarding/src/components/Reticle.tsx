/**
 * The nose-ball reticle: FIFA4ALL's signature motif.
 *
 * Zone geometry is drawn from the thresholds published by the bridge, so what
 * the user sees is exactly what the input logic uses (TECHNICAL_SPEC.md).
 */

import type { ControlState, Direction, Thresholds } from "../types";
import { Ball } from "./Ball";
import "./Reticle.css";

/** Nose offset, in normalized units, mapped to the outer edge of the widget. */
const VISIBLE_RANGE = 0.17;

const LABELS: ReadonlyArray<{ key: string; direction: Direction; x: number; y: number }> = [
  { key: "W", direction: "N", x: 0, y: -1 },
  { key: "D", direction: "E", x: 1, y: 0 },
  { key: "S", direction: "S", x: 0, y: 1 },
  { key: "A", direction: "W", x: -1, y: 0 },
];

interface ReticleProps {
  readonly state: ControlState;
  readonly thresholds: Thresholds;
  readonly size?: number;
  /** Fill 0-1 of the lock-on ring, used by the calibration dwell. */
  readonly lockProgress?: number;
  readonly locked?: boolean;
  readonly showKeys?: boolean;
}

export function Reticle({
  state,
  thresholds,
  size = 260,
  lockProgress = 0,
  locked = false,
  showKeys = true,
}: ReticleProps) {
  const half = size / 2;
  const scale = half / VISIBLE_RANGE;
  const neutral = thresholds.exit_radius * scale;
  const inner = thresholds.enter_radius * scale;

  // Clamp the ball to the widget so a large head movement never escapes it.
  const raw = { x: state.nose.x * scale, y: state.nose.y * scale };
  const distance = Math.hypot(raw.x, raw.y);
  const limit = half - 12;
  const clamp = distance > limit ? limit / distance : 1;
  const ball = { x: raw.x * clamp, y: raw.y * clamp };

  const circumference = 2 * Math.PI * neutral;
  const moving = state.direction !== null;

  return (
    <div className={`reticle ${locked ? "is-locked" : ""}`} style={{ width: size, height: size }}>
      <svg viewBox={`${-half} ${-half} ${size} ${size}`} width={size} height={size}>
        {/* Radar rings and crosshair */}
        <circle className="reticle__radar" r={half - 6} />
        <circle className="reticle__radar" r={(half - 6) * 0.66} />
        <line className="reticle__cross" x1={-half + 6} y1={0} x2={half - 6} y2={0} />
        <line className="reticle__cross" x1={0} y1={-half + 6} x2={0} y2={half - 6} />

        {/* Diagonal zone dividers, drawn at the 45-degree zone boundaries. */}
        {[45, 135, 225, 315].map((angle) => {
          const radians = (angle * Math.PI) / 180;
          return (
            <line
              key={angle}
              className="reticle__divider"
              x1={Math.cos(radians) * neutral}
              y1={Math.sin(radians) * neutral}
              x2={Math.cos(radians) * (half - 6)}
              y2={Math.sin(radians) * (half - 6)}
            />
          );
        })}

        {/* Dead zone: inner ring is the release radius, outer is the trigger. */}
        <circle className="reticle__inner" r={inner} />
        <circle className={`reticle__neutral ${moving ? "is-active" : ""}`} r={neutral} />

        {/* Lock-on progress ring for calibration. */}
        {lockProgress > 0 && (
          <circle
            className="reticle__lock"
            r={neutral}
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - lockProgress)}
            transform="rotate(-90)"
          />
        )}

        {/* Active direction wedge. */}
        {state.direction !== null && (
          <path className="reticle__wedge" d={wedgePath(state.direction, neutral, half - 6)} />
        )}
      </svg>

      {showKeys &&
        LABELS.map((label) => (
          <span
            key={label.key}
            className={`reticle__key ${(state.keys as readonly string[]).includes(label.key) ? "is-active" : ""}`}
            style={{
              transform: `translate(-50%, -50%) translate(${label.x * (half - 14)}px, ${
                label.y * (half - 14)
              }px)`,
            }}
          >
            {label.key}
          </span>
        ))}

      <div
        className="reticle__ball"
        style={{ transform: `translate(-50%, -50%) translate(${ball.x}px, ${ball.y}px)` }}
      >
        <Ball size={26} spin={moving} />
      </div>

      {!state.tracking && <div className="reticle__lost">TRACKING LOST</div>}
    </div>
  );
}

/** Build a 45-degree wedge for the active direction zone. */
function wedgePath(direction: Direction, from: number, to: number): string {
  const centers: Record<Direction, number> = {
    E: 0, NE: -45, N: -90, NW: -135, W: 180, SW: 135, S: 90, SE: 45,
  };
  const mid = centers[direction];
  const start = ((mid - 22.5) * Math.PI) / 180;
  const end = ((mid + 22.5) * Math.PI) / 180;
  const point = (radius: number, angle: number) =>
    `${(Math.cos(angle) * radius).toFixed(2)} ${(Math.sin(angle) * radius).toFixed(2)}`;
  return [
    `M ${point(from, start)}`,
    `L ${point(to, start)}`,
    `A ${to} ${to} 0 0 1 ${point(to, end)}`,
    `L ${point(from, end)}`,
    `A ${from} ${from} 0 0 0 ${point(from, start)}`,
    "Z",
  ].join(" ");
}
