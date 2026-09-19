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
}

export function useControlState(): ControlChannel {
  const [state, setState] = useState<ControlState>(IDLE_STATE);
  const [config, setConfig] = useState<BridgeConfig>(MOCK_CONFIG);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [useMock, setUseMock] = useState(false);
  const [mockInput, setMockInput] = useState<MockInput>(IDLE_MOCK_INPUT);

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
      setState(payload as ControlState);
    };
    stream.onerror = () => {
      setStatus("error");
      setError("lost connection to the tracking bridge");
    };
    return () => stream.close();
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

  return {
    state,
    config: useMock ? MOCK_CONFIG : config,
    status: useMock ? "mock" : status,
    error,
    mockInput,
    setMockInput,
    useMock,
    setUseMock,
    calibrate,
  };
}

function isBridgeError(payload: unknown): payload is { error: string } {
  return (
    typeof payload === "object" &&
    payload !== null &&
    typeof (payload as { error?: unknown }).error === "string"
  );
}
