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
  /** How long the gesture has been held. Shot power comes from this. */
  readonly held_seconds?: number;
  /** Which eye is winking, when one clearly is. */
  readonly eye?: "left" | "right" | null;
}

export interface ControlState {
  readonly centered: boolean;
  readonly nose: { readonly x: number; readonly y: number };
  /** Absolute nose position in the mirrored camera image, normalized 0-1. */
  readonly nose_point?: { readonly x: number; readonly y: number } | null;
  /** Calibrated neutral position in the same space. */
  readonly center_point?: { readonly x: number; readonly y: number } | null;
  readonly direction: Direction | null;
  readonly keys: readonly MovementKey[];
  readonly mouth: ExpressionState;
  readonly wink: ExpressionState;
  /** Raised-eyebrow recentres pose. Absent in older payloads. */
  readonly eyebrow?: ExpressionState;
  readonly tracking: boolean;
  /** True only on the frame neutral was re-established after posture drift. */
  readonly recentred?: boolean;
  /** Present once the bridge is running; absent in pure mock mode. */
  readonly armed?: boolean;
  /** Keys the output layer is physically holding right now. */
  readonly held_keys?: readonly string[];
  /** How long the mouth has been open, which is shot power. */
  readonly shot_seconds?: number;
  /** Name of the app that currently owns the keyboard. */
  readonly frontmost?: string | null;
  /** True when a browser is frontmost and could be receiving the keys. */
  readonly game_focus?: boolean;
}

export interface Thresholds {
  readonly enter_radius: number;
  readonly exit_radius: number;
  readonly y_scale: number;
  readonly angle_margin: number;
  readonly recentre_seconds: number;
  readonly recentre_stillness: number;
  readonly mouth_open: number;
  readonly mouth_reset: number;
  readonly wink_on: number;
  readonly wink_off: number;
  readonly brow_on?: number;
  readonly brow_off?: number;
  /** A wink only counts while the other eye stays this open, so blinks are
   *  rejected: eyelids close out of sync and briefly look like a wink. */
  readonly eye_open_fraction: number;
  readonly eye_open_floor: number;
  readonly dwell_seconds: number;
}

export interface BridgeConfig {
  readonly thresholds: Thresholds;
  readonly direction_keys: Readonly<Record<Direction, readonly MovementKey[]>>;
  readonly has_video: boolean;
  /** Why keyboard output cannot work, or null when it can. */
  readonly keyboard_problem?: string | null;
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
  angle_margin: 9.0,
  recentre_seconds: 3.5,
  recentre_stillness: 0.012,
  mouth_open: 0.09,
  mouth_reset: 0.06,
  wink_on: 0.025,
  wink_off: 0.015,
  brow_on: 0.030,
  brow_off: 0.012,
  eye_open_fraction: 0.65,
  eye_open_floor: 0.07,
  dwell_seconds: 1.0,
};

/** Mouth-open duration that counts as a full-power shot, in seconds. */
export const FULL_SHOT_SECONDS = 1.25;
