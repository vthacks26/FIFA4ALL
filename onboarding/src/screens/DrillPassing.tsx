/**
 * Screen 6 - Drill 03: Passing.
 *
 * Each wink edge fires one pass: the ball travels along a dotted trajectory and
 * the teammate receives it. Three successful passes confirm the gesture.
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

const REQUIRED_PASSES = 3;

interface DrillPassingProps {
  readonly channel: ControlChannel;
  readonly onComplete: () => void;
}

export function DrillPassing({ channel, onComplete }: DrillPassingProps) {
  const { state, config } = channel;
  const [completed, setCompleted] = useState(0);
  const [passId, setPassId] = useState(0);
  const [passing, setPassing] = useState(false);
  const [receiving, setReceiving] = useState(false);

  useGestureEdge(state.wink.active, () => {
    if (completed >= REQUIRED_PASSES) return;
    setPassId((id) => id + 1);
    setPassing(true);
    window.setTimeout(() => setPassing(false), 420);
    window.setTimeout(() => setReceiving(true), 640);
    window.setTimeout(() => {
      setReceiving(false);
      setCompleted((count) => Math.min(count + 1, REQUIRED_PASSES));
    }, 1000);
  });

  const finished = completed >= REQUIRED_PASSES;
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
        <p className="eyebrow">Drill 03</p>
        <h1 className="drill__title">Wink to pass</h1>
        <p className="lede">Wink with either eye to play the ball to your teammate.</p>
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
            label="Detecting wink"
            value={state.wink.confidence}
            active={state.wink.active}
            tone="purple"
          />
        </div>

        <div className="drill__pitch drill__pitch--pass">
          <div className="drill__pitch-lines" />

          <div className="drill__passers">
            <Player pose={passing ? "pass" : "idle"} kit="purple" size={210} />
            <Player
              pose={receiving ? "receive" : "idle"}
              kit="teal"
              size={195}
            />
          </div>

          {passId > 0 && (
            <svg className="pass-trail" key={`trail-${passId}`} viewBox="0 0 200 60">
              <path d="M2 54 Q 100 -12 196 50" />
            </svg>
          )}
          {passId > 0 && (
            <div className="pass-ball" key={passId}>
              <Ball size={22} spin />
            </div>
          )}
        </div>

        <div className="drill__side">
          <Checklist
            title="Passes completed"
            items={Array.from({ length: REQUIRED_PASSES }, (_, index) => ({
              id: `pass-${index}`,
              label: `Pass ${index + 1}`,
              done: index < completed,
              active: index === completed,
            }))}
          />
        </div>
      </div>

      <p className={`drill__status ${finished ? "is-done" : ""}`}>
        {finished ? "Passing complete" : `${completed} of ${REQUIRED_PASSES} passes completed`}
      </p>
    </section>
  );
}
