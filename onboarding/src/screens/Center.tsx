/**
 * Screen 3 - Find your center.
 *
 * Holding the nose-ball still inside the neutral circle for the dwell period
 * fills the lock ring and calibrates that position as neutral.
 */

import { useEffect, useRef, useState } from "react";

import { StepRail } from "../components/StepRail";
import { CameraFrame } from "../components/CameraFrame";
import { Checklist } from "../components/Checklist";
import type { ControlChannel } from "../control/useControlState";
import { useHoldProgress } from "../control/hooks";
import "./Center.css";

interface CenterProps {
  readonly channel: ControlChannel;
  readonly onNext: () => void;
}

export function Center({ channel, onNext }: CenterProps) {
  const { state, config, calibrate } = channel;
  const [locked, setLocked] = useState(false);

  const holding = state.tracking && state.centered && !locked;
  const progress = useHoldProgress(holding, config.thresholds.dwell_seconds);

  const nextRef = useRef(onNext);
  nextRef.current = onNext;
  const fired = useRef(false);

  // Lock once the dwell completes. A ref guards against re-entry, because
  // locking stops the hold and resets progress back to zero.
  useEffect(() => {
    if (progress < 1 || fired.current) return;
    fired.current = true;
    setLocked(true);
    calibrate();
  }, [progress, calibrate]);

  // Advance after the lock-on animation. `locked` only ever flips once, so the
  // timer is never cancelled by a re-render.
  useEffect(() => {
    if (!locked) return;
    const timer = window.setTimeout(() => nextRef.current(), 1150);
    return () => window.clearTimeout(timer);
  }, [locked]);

  return (
    <section className="screen center">
      <div className="pitch-bg" />

      <header className="center__header">
        <StepRail phase="CENTER_CALIBRATION" />
        <p className="eyebrow">Calibration</p>
        <h1 className="center__title">Find your center</h1>
        <p className="lede">
          Sit comfortably and look at the screen. Keep the ball in the middle &mdash; this becomes
          your neutral position.
        </p>
      </header>

      <div className="center__stage">
        <CameraFrame
          state={state}
          thresholds={config.thresholds}
          hasVideo={config.has_video}
          size={368}
          lockProgress={locked ? 1 : progress}
          locked={locked}
          showKeys={false}
        />

        <div className="center__side">
          <Checklist
            title="Getting ready"
            items={[
              {
                id: "camera",
                label: config.has_video ? "Camera detected" : "Simulated input",
                done: config.has_video || state.tracking,
              },
              { id: "face", label: "Face tracked", done: state.tracking },
              {
                id: "center",
                label: "Center position set",
                done: locked,
                active: state.tracking && !locked,
              },
            ]}
          />

          <div className="center__tips panel">
            <h3>Tips</h3>
            <ul>
              <li>Sit comfortably</li>
              <li>Keep your face in frame</li>
              <li>Look at the screen</li>
            </ul>
          </div>
        </div>
      </div>

      <p className={`center__status ${locked ? "is-locked" : ""}`}>
        {locked ? "Center found" : state.tracking ? "Hold still…" : "Looking for your face…"}
      </p>
    </section>
  );
}
