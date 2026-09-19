/** Control-state sources: the live bridge, or a mock for visual development. */

import {
  DEFAULT_THRESHOLDS,
  IDLE_STATE,
  type BridgeConfig,
  type ControlState,
} from "../types";

export const BRIDGE_URL =
  (import.meta.env.VITE_BRIDGE_URL as string | undefined) ??
  (import.meta.env.DEV ? "http://127.0.0.1:8765" : "");

export const MOCK_CONFIG: BridgeConfig = {
  thresholds: DEFAULT_THRESHOLDS,
  direction_keys: {
    N: ["W"],
    NE: ["W", "D"],
    E: ["D"],
    SE: ["S", "D"],
    S: ["S"],
    SW: ["S", "A"],
    W: ["A"],
    NW: ["W", "A"],
  },
  has_video: false,
};

/** Simulated inputs the dev panel can drive without a webcam. */
export interface MockInput {
  readonly x: number;
  readonly y: number;
  readonly mouth: boolean;
  readonly wink: boolean;
  readonly tracking: boolean;
}

export const IDLE_MOCK_INPUT: MockInput = {
  x: 0,
  y: 0,
  mouth: false,
  wink: false,
  tracking: true,
};

/**
 * Derive control state from simulated input using the same rules as Python.
 *
 * This mirrors `tracking/controls.py` so mock mode behaves like the real
 * pipeline. Hysteresis needs the previous state, so it is passed in.
 */
export function deriveMockState(
  input: MockInput,
  previous: ControlState,
  config: BridgeConfig,
): ControlState {
  if (!input.tracking) {
    return { ...IDLE_STATE, tracking: false };
  }

  const { thresholds } = config;
  const radius = Math.hypot(input.x, input.y * thresholds.y_scale);
  const wasMoving = previous.direction !== null;
  const boundary = wasMoving ? thresholds.enter_radius : thresholds.exit_radius;
  const direction = radius >= boundary ? classifyDirection(input.x, input.y) : null;

  const mouthValue = input.mouth ? thresholds.mouth_open * 1.6 : 0;
  const winkValue = input.wink ? thresholds.wink_on * 1.6 : 0;

  return {
    centered: direction === null,
    nose: { x: input.x, y: input.y },
    direction,
    keys: direction === null ? [] : [...config.direction_keys[direction]],
    mouth: {
      active: input.mouth,
      fired: input.mouth && !previous.mouth.active,
      value: mouthValue,
      confidence: Math.min(mouthValue / thresholds.mouth_open, 1),
    },
    wink: {
      active: input.wink,
      fired: input.wink && !previous.wink.active,
      value: winkValue,
      confidence: Math.min(winkValue / thresholds.wink_on, 1),
    },
    tracking: true,
  };
}

/** Map an offset onto one of eight 45-degree zones. Image y grows downward. */
export function classifyDirection(dx: number, dy: number) {
  const degrees = (Math.atan2(-dy, dx) * 180) / Math.PI;
  const shifted = (degrees + 22.5 + 360) % 360;
  const zones = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"] as const;
  return zones[Math.floor(shifted / 45)];
}
