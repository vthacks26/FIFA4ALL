/**
 * Screen 4 - Drill 01: Movement.
 *
 * The player runs in place and rotates to face the detected direction, so the
 * user learns what their head motion means before entering EA Sports FC.
 * Validation covers the four cardinals; diagonals are shown but not required.
 */

import { useEffect, useRef, useState } from "react";

import { CameraFrame } from "../components/CameraFrame";
import { Checklist } from "../components/Checklist";
import { Player } from "../components/Player";
import type { ControlChannel } from "../control/useControlState";
import { useHoldProgress } from "../control/hooks";
import type { Direction } from "../types";
import "./Drill.css";

/** Held intentionally for this long before a direction counts as learned. */
const HOLD_SECONDS = 0.7;

const TARGETS: ReadonlyArray<{ id: Direction; label: string }> = [
  { id: "N", label: "Run North" },
  { id: "S", label: "Run South" },
  { id: "W", label: "Run Left" },
  { id: "E", label: "Run Right" },
];

interface DrillMovementProps {
  readonly channel: ControlChannel;
  readonly onComplete: () => void;
}

export function DrillMovement({ channel, onComplete }: DrillMovementProps) {
  const { state, config } = channel;
  const [done, setDone] = useState<readonly Direction[]>([]);

  const next = TARGETS.find((target) => !done.includes(target.id));
  const onTarget = next !== undefined && state.direction === next.id;
  const progress = useHoldProgress(onTarget, HOLD_SECONDS);

  useEffect(() => {
    if (progress >= 1 && next !== undefined && !done.includes(next.id)) {
      setDone((current) => [...current, next.id]);
    }
  }, [progress, next, done]);

  const finished = done.length === TARGETS.length;
  const completeRef = useRef(onComplete);
  completeRef.current = onComplete;

  useEffect(() => {
    if (!finished) return;
    const timer = window.setTimeout(() => completeRef.current(), 1500);
    return () => window.clearTimeout(timer);
  }, [finished]);

  return (
    <section className="screen drill">
      <div className="pitch-bg" />

      <header className="drill__header">
        <p className="eyebrow">Drill 01</p>
        <h1 className="drill__title">Movement</h1>
        <p className="lede">
          Keep the ball in the center to stand still. Move your head outside the circle to run.
        </p>
      </header>

      <div className="drill__stage">
        <CameraFrame
          state={state}
          thresholds={config.thresholds}
          hasVideo={config.has_video}
          size={330}
        />

        <div className="drill__pitch">
          <div className="drill__pitch-lines" />
          <Player
            pose={state.direction === null ? "idle" : "run"}
            kit="lime"
            facing={state.direction}
            size={300}
          />
          <div className={`drill__direction ${state.direction !== null ? "is-active" : ""}`}>
            {state.direction ?? "STOPPED"}
          </div>
        </div>

        <div className="drill__side">
          <Checklist
            title="Movement check"
            items={TARGETS.map((target) => ({
              id: target.id,
              label: target.label,
              done: done.includes(target.id),
              active: next?.id === target.id,
            }))}
          />
          {next !== undefined && (
            <div className="drill__prompt panel">
              <span className="drill__prompt-label">Next</span>
              <strong>{next.label}</strong>
              <div className="drill__hold">
                <div className="drill__hold-fill" style={{ width: `${progress * 100}%` }} />
              </div>
            </div>
          )}
        </div>
      </div>

      <p className={`drill__status ${finished ? "is-done" : ""}`}>
        {finished ? "Movement complete" : `${done.length} of ${TARGETS.length} directions learned`}
      </p>
    </section>
  );
}
