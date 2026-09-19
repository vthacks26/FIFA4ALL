/**
 * FIFA4ALL orientation shell.
 *
 * Owns the phase state machine, persists progress across refreshes, and plays a
 * ball wipe between screens. Control data comes from one channel, so every
 * screen behaves the same whether it is live or simulated.
 */

import { useCallback, useEffect, useState } from "react";

import { Ball } from "./components/Ball";
import { DevPanel } from "./components/DevPanel";
import { useControlState } from "./control/useControlState";
import { Center } from "./screens/Center";
import { Complete } from "./screens/Complete";
import { Controls } from "./screens/Controls";
import { DrillMovement } from "./screens/DrillMovement";
import { DrillPassing } from "./screens/DrillPassing";
import { DrillShooting } from "./screens/DrillShooting";
import { Live } from "./screens/Live";
import { Transition } from "./screens/Transition";
import { Welcome } from "./screens/Welcome";
import { usePersistentState } from "./control/hooks";
import { PHASE_ORDER, type Phase } from "./types";
import "./App.css";

const WIPE_MS = 560;

export default function App() {
  const channel = useControlState();
  const [phase, setPhase] = usePersistentState<Phase>("fifa4all.phase", "WELCOME");
  const [wiping, setWiping] = useState(false);
  const [devOpen, setDevOpen] = useState(false);

  /** Advance with a ball wipe covering the screen swap. */
  const goTo = useCallback(
    (next: Phase) => {
      setWiping(true);
      window.setTimeout(() => setPhase(next), WIPE_MS * 0.48);
      window.setTimeout(() => setWiping(false), WIPE_MS);
    },
    [setPhase],
  );

  const advance = useCallback(() => {
    const index = PHASE_ORDER.indexOf(phase);
    const next = PHASE_ORDER[Math.min(index + 1, PHASE_ORDER.length - 1)];
    goTo(next);
  }, [phase, goTo]);

  const restart = useCallback(() => goTo("WELCOME"), [goTo]);

  // Let a presenter step through the flow from the keyboard during the demo.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowRight") advance();
      if (event.key === "`") setDevOpen((open) => !open);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [advance]);

  return (
    <main className="app">
      {renderPhase()}

      <div className={`wipe ${wiping ? "is-active" : ""}`} aria-hidden="true">
        <div className="wipe__ball">
          <Ball size={120} spin />
        </div>
      </div>

      <DevPanel
        channel={channel}
        open={devOpen}
        onToggle={() => setDevOpen((open) => !open)}
        onRestart={restart}
      />
    </main>
  );

  function renderPhase() {
    switch (phase) {
      case "WELCOME":
        return <Welcome key="welcome" onStart={advance} />;
      case "EXPLAIN_CONTROLS":
        return <Controls key="controls" onNext={advance} />;
      case "CENTER_CALIBRATION":
        return <Center key="center" channel={channel} onNext={advance} />;
      case "MOVEMENT_TRAINING":
        return <DrillMovement key="movement" channel={channel} onComplete={advance} />;
      case "SHOOTING_TRAINING":
        return <DrillShooting key="shooting" channel={channel} onComplete={advance} />;
      case "PASSING_TRAINING":
        return <DrillPassing key="passing" channel={channel} onComplete={advance} />;
      case "COMPLETE":
        return <Complete key="complete" channel={channel} onNext={advance} />;
      case "TRANSITION":
        return <Transition key="transition" onDone={advance} />;
      case "LIVE_TELEMETRY":
        return <Live key="live" channel={channel} onRestart={restart} />;
    }
  }
}
