/** Wire contract shared with the Python bridge (see TECHNICAL_SPEC.md). */

export type Direction = "N" | "NE" | "E" | "SE" | "S" | "SW" | "W" | "NW";

export type MovementKey = "W" | "A" | "S" | "D";

export interface ExpressionState {
  readonly active: boolean;
  /** True only on the frame the gesture crossed its trigger threshold. */
  readonly fired: boolean;
  readonly value: number | null;
  /** Progress toward the trigger threshold, clamped to [0, 1]. */
  readonly confidence: number;
}

export interface ControlState {
  readonly centered: boolean;
  readonly nose: { readonly x: number; readonly y: number };
  readonly direction: Direction | null;
  readonly keys: readonly MovementKey[];
  readonly mouth: ExpressionState;
  readonly wink: ExpressionState;
  readonly tracking: boolean;
}

export interface Thresholds {
  readonly enter_radius: number;
  readonly exit_radius: number;
  readonly y_scale: number;
  readonly mouth_open: number;
  readonly mouth_reset: number;
  readonly wink_on: number;
  readonly wink_off: number;
  readonly dwell_seconds: number;
}

export interface BridgeConfig {
  readonly thresholds: Thresholds;
  readonly direction_keys: Readonly<Record<Direction, readonly MovementKey[]>>;
  readonly has_video: boolean;
}

/** Orientation phases, in the order defined by TECHNICAL_SPEC.md. */
export type Phase =
  | "WELCOME"
  | "EXPLAIN_CONTROLS"
  | "CENTER_CALIBRATION"
  | "MOVEMENT_TRAINING"
  | "SHOOTING_TRAINING"
  | "PASSING_TRAINING"
  | "COMPLETE"
  | "TRANSITION"
  | "LIVE_TELEMETRY";

export const PHASE_ORDER: readonly Phase[] = [
  "WELCOME",
  "EXPLAIN_CONTROLS",
  "CENTER_CALIBRATION",
  "MOVEMENT_TRAINING",
  "SHOOTING_TRAINING",
  "PASSING_TRAINING",
  "COMPLETE",
  "TRANSITION",
  "LIVE_TELEMETRY",
];

export const IDLE_STATE: ControlState = {
  centered: true,
  nose: { x: 0, y: 0 },
  direction: null,
  keys: [],
  mouth: { active: false, fired: false, value: null, confidence: 0 },
  wink: { active: false, fired: false, value: null, confidence: 0 },
  tracking: false,
};

export const DEFAULT_THRESHOLDS: Thresholds = {
  enter_radius: 0.045,
  exit_radius: 0.062,
  y_scale: 1.15,
  mouth_open: 0.09,
  mouth_reset: 0.06,
  wink_on: 0.025,
  wink_off: 0.015,
  dwell_seconds: 1.0,
};
