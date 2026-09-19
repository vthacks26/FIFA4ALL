/**
 * Screen 5 - Drill 02: Shooting.
 *
 * Each mouth-open edge fires one shot: input flash, kick animation, ball travel,
 * net ripple, goal burst. Three successful activations confirm the gesture.
 */

import { useEffect, useRef, useState } from "react";

import { Ball } from "../components/Ball";
import { CameraFrame } from "../components/CameraFrame";
import { Checklist } from "../components/Checklist";
import { ConfidenceBar } from "../components/ConfidenceBar";
import { Player } from "../components/Player";
import type { ControlChannel } from "../control/useControlState";
import { useGestureEdge } from "../control/hooks";
import "./Drill.css";

const REQUIRED_SHOTS = 3;

interface DrillShootingProps {
  readonly channel: ControlChannel;
  readonly onComplete: () => void;
}

export function DrillShooting({ channel, onComplete }: DrillShootingProps) {
  const { state, config } = channel;
  const [scored, setScored] = useState(0);
  // Incrementing key restarts the CSS animations on every shot.
  const [shotId, setShotId] = useState(0);
  const [kicking, setKicking] = useState(false);

  useGestureEdge(state.mouth.active, () => {
    if (scored >= REQUIRED_SHOTS) return;
    setShotId((id) => id + 1);
    setKicking(true);
    window.setTimeout(() => setScored((count) => Math.min(count + 1, REQUIRED_SHOTS)), 620);
    window.setTimeout(() => setKicking(false), 700);
  });

  const finished = scored >= REQUIRED_SHOTS;
  const completeRef = useRef(onComplete);
  completeRef.current = onComplete;

  useEffect(() => {
    if (!finished) return;
    const timer = window.setTimeout(() => completeRef.current(), 1600);
    return () => window.clearTimeout(timer);
  }, [finished]);

  return (
    <section className="screen drill">
      <div className="pitch-bg" />

      <header className="drill__header">
        <p className="eyebrow">Drill 02</p>
        <h1 className="drill__title">Open to shoot</h1>
        <p className="lede">Open your mouth like an &ldquo;O&rdquo; to strike the ball.</p>
      </header>

      <div className="drill__stage">
        <div className="drill__camera-col">
          <CameraFrame
            state={state}
            thresholds={config.thresholds}
            hasVideo={config.has_video}
            size={300}
            showKeys={false}
          />
          <ConfidenceBar
            label="Detecting mouth"
            value={state.mouth.confidence}
            active={state.mouth.active}
            tone="amber"
          />
        </div>

        <div className={`drill__pitch drill__pitch--shoot ${kicking ? "drill__shake" : ""}`}>
          <div className="drill__pitch-lines" />

          <div className={`goal ${kicking ? "is-scored" : ""}`}>
            <div className={`goal__burst ${kicking ? "is-on" : ""}`}>GOAL!</div>
          </div>

          <div className="drill__shooter">
            <Player pose={kicking ? "shoot" : "idle"} kit="amber" size={190} />
          </div>

          {shotId > 0 && (
            <div className="shot-ball" key={shotId}>
              <Ball size={24} spin />
            </div>
          )}
        </div>

        <div className="drill__side">
          <Checklist
            title="Shots on target"
            items={Array.from({ length: REQUIRED_SHOTS }, (_, index) => ({
              id: `shot-${index}`,
              label: `Shot ${index + 1}`,
              done: index < scored,
              active: index === scored,
            }))}
          />
        </div>
      </div>

      <p className={`drill__status ${finished ? "is-done" : ""}`}>
        {finished ? "Shooting complete" : `${scored} of ${REQUIRED_SHOTS} shots scored`}
      </p>
    </section>
  );
}
