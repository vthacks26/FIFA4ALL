/**
 * Screen 9 - Live match telemetry.
 *
 * Stays on the second monitor while the user plays EA Sports FC. A spectator
 * standing behind them should be able to read it from several feet away, so it
 * carries only the four things that prove the face is driving the game.
 */

import { CameraFrame } from "../components/CameraFrame";
import { ConfidenceBar } from "../components/ConfidenceBar";
import { Logo } from "../components/Logo";
import type { ControlChannel } from "../control/useControlState";
import type { MovementKey } from "../types";
import "./Live.css";

const KEY_ROWS: ReadonlyArray<readonly MovementKey[]> = [["W"], ["A", "S", "D"]];

interface LiveProps {
  readonly channel: ControlChannel;
  readonly onRestart: () => void;
}

export function Live({ channel, onRestart }: LiveProps) {
  const { state, config, status } = channel;
  const confidence = state.tracking ? 96 : 0;

  return (
    <section className="screen live">
      <div className="pitch-bg" />

      <header className="live__header">
        <div className="live__brand">
          <Logo size={30} />
          <span className="live__badge">LIVE</span>
        </div>
        <p className="live__sub">Your controls are active.</p>
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
              <span className="live-row__name">Shoot</span>
              <span className="live-row__gesture">Mouth open</span>
            </div>
            <div className="live-row__body">
              <strong className="live-row__value">
                {state.mouth.active ? "FIRING" : "READY"}
              </strong>
              <span className={`keycap keycap--wide ${state.mouth.active ? "is-down" : ""}`}>
                Space
              </span>
            </div>
            <ConfidenceBar
              label="Mouth"
              value={state.mouth.confidence}
              active={state.mouth.active}
              tone="amber"
            />
          </article>

          <article className={`live-row live-row--purple ${state.wink.active ? "is-active" : ""}`}>
            <div className="live-row__head">
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

      <footer className="live__footer">
        <div className="live__confidence">
          <ConfidenceBar
            label={`Control confidence — ${status}`}
            value={confidence / 100}
            active={state.tracking}
          />
        </div>
        <p className="live__motto">Play without limits.</p>
        <button className="btn btn--ghost live__restart" onClick={onRestart} type="button">
          Redo training
        </button>
      </footer>
    </section>
  );
}
