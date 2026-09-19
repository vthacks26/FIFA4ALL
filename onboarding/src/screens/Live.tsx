/**
 * Screen 9 - Live match telemetry.
 *
 * Stays on the second monitor while the user plays EA Sports FC. A spectator
 * standing behind them should be able to read it from several feet away, so it
 * carries only the four things that prove the face is driving the game.
 */

import { useEffect, useState } from "react";

import { CameraFrame } from "../components/CameraFrame";
import { ConfidenceBar } from "../components/ConfidenceBar";
import { Logo } from "../components/Logo";
import { MatchStatus } from "../components/MatchStatus";
import { IconBadge, MoveIcon, PassIcon, ShootIcon } from "../components/icons";
import type { ControlChannel } from "../control/useControlState";
import { FULL_SHOT_SECONDS, type MovementKey } from "../types";
import "./Live.css";

const KEY_ROWS: ReadonlyArray<readonly MovementKey[]> = [["W"], ["A", "S", "D"]];

interface LiveProps {
  readonly channel: ControlChannel;
  readonly onRestart: () => void;
}

export function Live({ channel, onRestart }: LiveProps) {
  const { state, config, status, setArmed, useMock, calibrate } = channel;
  const confidence = state.tracking ? 96 : 0;
  // Shot power is how long the mouth has stayed open, capped for display.
  const heldSeconds = state.mouth.held_seconds ?? 0;
  const shotPower = Math.min(heldSeconds / FULL_SHOT_SECONDS, 1);
  const recentred = useRecentreNotice(state.recentred === true);

  return (
    <section className="screen live">
      <div className="pitch-bg" />

      <header className="live__header">
        <div className="live__brand">
          <Logo size={30} />
          <span className="live__badge">LIVE</span>
        </div>
        <MatchStatus
          state={state}
          onArm={setArmed}
          keyboardProblem={config.keyboard_problem}
          disabled={useMock}
        />
      </header>

      <div className="live__stage">
        <CameraFrame
          state={state}
          thresholds={config.thresholds}
          hasVideo={config.has_video}
          size={390}
        />

        <div className="live__panels">
          <article className={`live-row ${state.direction !== null ? "is-active" : ""}`}>
            <div className="live-row__head">
              <IconBadge tone="lime" size={40} active={state.direction !== null}>
                <MoveIcon size={22} active={state.direction !== null} />
              </IconBadge>
              <span className="live-row__name">Move</span>
              <span className="live-row__gesture">Head movement</span>
            </div>
            <div className="live-row__body">
              <strong className="live-row__value">{state.direction ?? "CENTER"}</strong>
              <div className="keycap-grid">
                {KEY_ROWS.map((row, index) => (
                  <div className="keycap-grid__row" key={index}>
                    {row.map((key) => (
                      <span
                        key={key}
                        className={`keycap ${state.keys.includes(key) ? "is-down" : ""}`}
                      >
                        {key}
                      </span>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </article>

          <article className={`live-row live-row--amber ${state.mouth.active ? "is-active" : ""}`}>
            <div className="live-row__head">
              <IconBadge tone="amber" size={40} active={state.mouth.active}>
                <ShootIcon size={22} active={state.mouth.active} />
              </IconBadge>
              <span className="live-row__name">Shoot</span>
              <span className="live-row__gesture">Mouth open</span>
            </div>
            <div className="live-row__body">
              <strong className="live-row__value">
                {state.mouth.active ? `CHARGING ${heldSeconds.toFixed(1)}s` : "READY"}
              </strong>
              <span className={`keycap keycap--wide ${state.mouth.active ? "is-down" : ""}`}>
                Space
              </span>
            </div>
            <ConfidenceBar
              label={state.mouth.active ? "Shot power" : "Mouth"}
              value={state.mouth.active ? shotPower : state.mouth.confidence}
              active={state.mouth.active}
              tone="amber"
            />
          </article>

          <article className={`live-row live-row--purple ${state.wink.active ? "is-active" : ""}`}>
            <div className="live-row__head">
              <IconBadge tone="purple" size={40} active={state.wink.active}>
                <PassIcon size={22} active={state.wink.active} />
              </IconBadge>
              <span className="live-row__name">Pass</span>
              <span className="live-row__gesture">Wink</span>
            </div>
            <div className="live-row__body">
              <strong className="live-row__value">{state.wink.active ? "FIRING" : "READY"}</strong>
              <span className={`keycap ${state.wink.active ? "is-down" : ""}`}>L</span>
            </div>
            <ConfidenceBar
              label="Wink"
              value={state.wink.confidence}
              active={state.wink.active}
              tone="purple"
            />
          </article>
        </div>
      </div>

      {recentred && <div className="live__toast">Neutral re-centred</div>}

      <footer className="live__footer">
        <div className="live__confidence">
          <ConfidenceBar
            label={`Control confidence — ${status}`}
            value={confidence / 100}
            active={state.tracking}
          />
        </div>
        <p className="live__motto">Play without limits.</p>
        <button
          className="btn btn--ghost live__restart"
          onClick={() => calibrate()}
          type="button"
          disabled={useMock}
        >
          Reset center
        </button>
        <button className="btn btn--ghost live__restart" onClick={onRestart} type="button">
          Redo training
        </button>
      </footer>
    </section>
  );
}

/**
 * Hold a re-centre notice on screen briefly.
 *
 * The bridge reports it for a single frame, which at 30fps is invisible.
 */
function useRecentreNotice(fired: boolean): boolean {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!fired) return;
    setVisible(true);
    const timer = window.setTimeout(() => setVisible(false), 1800);
    return () => window.clearTimeout(timer);
  }, [fired]);

  return visible;
}
