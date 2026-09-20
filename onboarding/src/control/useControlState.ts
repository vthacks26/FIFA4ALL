/**
 * Connects the UI to a control-state source.
 *
 * Live mode streams from the Python bridge over Server-Sent Events. Mock mode
 * derives state locally from the dev panel so the orientation screens can be
 * built and demoed with no webcam attached.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  IDLE_STATE,
  type BridgeConfig,
  type ControlState,
  type DeadzoneMode,
} from "../types";
import {
  BRIDGE_URL,
  IDLE_MOCK_INPUT,
  MOCK_CONFIG,
  deriveMockState,
  type MockInput,
} from "./source";

export type ConnectionStatus = "connecting" | "live" | "mock" | "error";

export interface ControlChannel {
  readonly state: ControlState;
  readonly config: BridgeConfig;
  readonly status: ConnectionStatus;
  readonly error: string | null;
  readonly mockInput: MockInput;
  readonly setMockInput: (next: MockInput) => void;
  readonly useMock: boolean;
  readonly setUseMock: (next: boolean) => void;
  readonly calibrate: () => void;
  /** Start or stop sending real key events to the focused application. */
  readonly setArmed: (next: boolean) => void;
  /** Current nose-deadzone mode (fixed default, or follow). */
  readonly deadzoneMode: DeadzoneMode;
  /** Persist the mode and apply it to live game control on this process. */
  readonly setDeadzoneMode: (next: DeadzoneMode) => void;
}

const DEADZONE_STORAGE = "fifa4all.deadzoneMode";

function readStoredDeadzoneMode(): DeadzoneMode | null {
  try {
    const stored = window.localStorage.getItem(DEADZONE_STORAGE);
    if (stored === null) return null;
    const parsed: unknown = JSON.parse(stored);
    if (parsed === "fixed" || parsed === "follow") return parsed;
  } catch {
    // Private mode or a corrupt value; fall through to the process default.
  }
  return null;
}

function writeStoredDeadzoneMode(mode: DeadzoneMode): void {
  try {
    window.localStorage.setItem(DEADZONE_STORAGE, JSON.stringify(mode));
  } catch {
    // Persistence is best-effort; the live POST still applies this session.
  }
}

function isDeadzoneMode(value: unknown): value is DeadzoneMode {
  return value === "fixed" || value === "follow";
}

export function useControlState(): ControlChannel {
  const [state, setState] = useState<ControlState>(IDLE_STATE);
  const [config, setConfig] = useState<BridgeConfig>(MOCK_CONFIG);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [useMock, setUseMock] = useState(false);
  const [mockInput, setMockInput] = useState<MockInput>(IDLE_MOCK_INPUT);
  const [deadzoneMode, setDeadzoneModeState] = useState<DeadzoneMode>(
    () => readStoredDeadzoneMode() ?? "fixed",
  );

  // Hysteresis and edge detection need the previous state without re-running
  // the effect on every frame.
  const previous = useRef<ControlState>(IDLE_STATE);
  previous.current = state;

  // Probe the bridge once; fall back to mock mode when it is not running.
  useEffect(() => {
    let cancelled = false;
    fetch(`${BRIDGE_URL}/config`)
      .then((response) => {
        if (!response.ok) throw new Error(`bridge responded ${response.status}`);
        return response.json() as Promise<BridgeConfig>;
      })
      .then((loaded) => {
        if (cancelled) return;
        setConfig(loaded);
        setStatus("live");
        setError(null);
        const stored = readStoredDeadzoneMode();
        if (stored === null && isDeadzoneMode(loaded.deadzone_mode)) {
          setDeadzoneModeState(loaded.deadzone_mode);
        }
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setConfig(MOCK_CONFIG);
        setUseMock(true);
        setStatus("mock");
        setError(reason instanceof Error ? reason.message : "bridge unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Live stream. Skipped entirely while mock mode is on.
  useEffect(() => {
    if (useMock || status === "connecting") return;

    const stream = new EventSource(`${BRIDGE_URL}/events`);
    stream.onmessage = (event: MessageEvent<string>) => {
      const payload: unknown = JSON.parse(event.data);
      if (isBridgeError(payload)) {
        setError(payload.error);
        setStatus("error");
        setState(IDLE_STATE);
        return;
      }
      setError(null);
      setStatus("live");
      const next = payload as ControlState;
      setState(next);
      if (isDeadzoneMode(next.deadzone_mode)) {
        setDeadzoneModeState(next.deadzone_mode);
      }
    };
    stream.onerror = () => {
      setStatus("error");
      setError("lost connection to the tracking bridge");
    };
    return () => stream.close();
  }, [useMock, status]);

  // A stored website choice wins over the process default, and POSTs onto
  // the same machine that injects WASD so play picks it up without a restart.
  useEffect(() => {
    if (useMock || status !== "live") return;
    const stored = readStoredDeadzoneMode();
    if (stored === null) return;
    void fetch(`${BRIDGE_URL}/deadzone-mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: stored }),
    })
      .then(async (response) => {
        if (!response.ok) return;
        const body: unknown = await response.json();
        const mode =
          typeof body === "object" && body !== null && "deadzone_mode" in body
            ? (body as { deadzone_mode: unknown }).deadzone_mode
            : stored;
        if (isDeadzoneMode(mode)) {
          setDeadzoneModeState(mode);
          setConfig((current) => ({ ...current, deadzone_mode: mode }));
        }
      })
      .catch(() => {
        // Toggle still shows the stored choice; the next click retries.
      });
  }, [useMock, status]);

  // Mock loop, driven at display rate so animations stay in step.
  useEffect(() => {
    if (!useMock) return;
    let frame = 0;
    const tick = () => {
      setState((current) => deriveMockState(mockInput, current, MOCK_CONFIG));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [useMock, mockInput]);

  const calibrate = useCallback(() => {
    if (useMock) return;
    void fetch(`${BRIDGE_URL}/calibrate`, { method: "POST" }).catch(() => {
      setError("could not reach the bridge to calibrate");
    });
  }, [useMock]);

  const setArmed = useCallback(
    (next: boolean) => {
      if (useMock) return;
      void fetch(`${BRIDGE_URL}/${next ? "arm" : "disarm"}`, { method: "POST" })
        .then(async (response) => {
          if (response.ok) {
            setError(null);
            return;
          }
          // The bridge refuses to arm when macOS would discard the keys, and
          // explains how to fix it. Surface that verbatim.
          const body: unknown = await response.json();
          const reason =
            typeof body === "object" && body !== null && "error" in body
              ? String((body as { error: unknown }).error)
              : "could not change input state";
          setError(reason);
        })
        .catch(() => setError("could not reach the bridge to change input state"));
    },
    [useMock],
  );

  const setDeadzoneMode = useCallback(
    (next: DeadzoneMode) => {
      writeStoredDeadzoneMode(next);
      setDeadzoneModeState(next);
      setConfig((current) => ({ ...current, deadzone_mode: next }));
      if (useMock) return;
      void fetch(`${BRIDGE_URL}/deadzone-mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: next }),
      })
        .then(async (response) => {
          if (response.ok) {
            setError(null);
            return;
          }
          const body: unknown = await response.json();
          const reason =
            typeof body === "object" && body !== null && "error" in body
              ? String((body as { error: unknown }).error)
              : "could not change deadzone mode";
          setError(reason);
        })
        .catch(() => setError("could not reach the bridge to change deadzone mode"));
    },
    [useMock],
  );

  return {
    state,
    config: useMock ? { ...MOCK_CONFIG, deadzone_mode: deadzoneMode } : config,
    status: useMock ? "mock" : status,
    error,
    mockInput,
    setMockInput,
    useMock,
    setUseMock,
    calibrate,
    setArmed,
    deadzoneMode,
    setDeadzoneMode,
  };
}

function isBridgeError(payload: unknown): payload is { error: string } {
  return (
    typeof payload === "object" &&
    payload !== null &&
    typeof (payload as { error?: unknown }).error === "string"
  );
}
