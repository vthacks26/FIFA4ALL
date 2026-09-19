/**
 * Development panel for building the orientation flow without a webcam.
 *
 * AGENT_HANDOFF requires simulating nose position, movement direction, the
 * mouth and wink triggers, and tracking lost/found.
 */

import type { ControlChannel } from "../control/useControlState";
import type { Direction } from "../types";
import "./DevPanel.css";

/** Offsets large enough to clear the dead zone in each direction. */
const NUDGE = 0.12;
const DIRECTIONS: ReadonlyArray<{ id: Direction; label: string; x: number; y: number }> = [
  { id: "NW", label: "↖", x: -NUDGE, y: -NUDGE },
  { id: "N", label: "↑", x: 0, y: -NUDGE },
  { id: "NE", label: "↗", x: NUDGE, y: -NUDGE },
  { id: "W", label: "←", x: -NUDGE, y: 0 },
  { id: "E", label: "→", x: NUDGE, y: 0 },
  { id: "SW", label: "↙", x: -NUDGE, y: NUDGE },
  { id: "S", label: "↓", x: 0, y: NUDGE },
  { id: "SE", label: "↘", x: NUDGE, y: NUDGE },
];

interface DevPanelProps {
  readonly channel: ControlChannel;
  readonly open: boolean;
  readonly onToggle: () => void;
  readonly onRestart: () => void;
}

export function DevPanel({ channel, open, onToggle, onRestart }: DevPanelProps) {
  const { mockInput, setMockInput, state, status, error, useMock, setUseMock } = channel;

  return (
    <div className={`dev ${open ? "is-open" : ""}`}>
      <button className="dev__toggle" onClick={onToggle} type="button">
        <span className={`dev__dot dev__dot--${status}`} />
        {status.toUpperCase()}
      </button>

      {open && (
        <div className="dev__body panel">
          <label className="dev__switch">
            <input
              type="checkbox"
              checked={useMock}
              onChange={(event) => setUseMock(event.target.checked)}
            />
            Simulate input
          </label>

          {error !== null && <p className="dev__error">{error}</p>}

          <fieldset className="dev__group" disabled={!useMock}>
            <legend>Nose direction</legend>
            <div className="dev__pad">
              {DIRECTIONS.slice(0, 3).map(renderButton)}
              {renderButton(DIRECTIONS[3])}
              <button
                type="button"
                className={`dev__pad-btn ${state.centered ? "is-on" : ""}`}
                onClick={() => setMockInput({ ...mockInput, x: 0, y: 0 })}
              >
                &middot;
              </button>
              {DIRECTIONS.slice(4).map(renderButton)}
            </div>
          </fieldset>

          <fieldset className="dev__group" disabled={!useMock}>
            <legend>Gestures</legend>
            <div className="dev__row">
              <button
                type="button"
                className={`dev__btn ${mockInput.mouth ? "is-on" : ""}`}
                onClick={() => setMockInput({ ...mockInput, mouth: !mockInput.mouth })}
              >
                Mouth / Space
              </button>
              <button
                type="button"
                className={`dev__btn ${mockInput.wink ? "is-on" : ""}`}
                onClick={() => setMockInput({ ...mockInput, wink: !mockInput.wink })}
              >
                Wink / L
              </button>
              <button
                type="button"
                className={`dev__btn ${!mockInput.tracking ? "is-on" : ""}`}
                onClick={() => setMockInput({ ...mockInput, tracking: !mockInput.tracking })}
              >
                {mockInput.tracking ? "Lose tracking" : "Regain tracking"}
              </button>
            </div>
          </fieldset>

          <button type="button" className="dev__btn dev__btn--wide" onClick={onRestart}>
            Restart orientation
          </button>

          <pre className="dev__state">
            {JSON.stringify(
              { dir: state.direction, keys: state.keys, track: state.tracking },
              null,
              1,
            )}
          </pre>
        </div>
      )}
    </div>
  );

  function renderButton(item: (typeof DIRECTIONS)[number]) {
    const isOn = state.direction === item.id;
    return (
      <button
        key={item.id}
        type="button"
        className={`dev__pad-btn ${isOn ? "is-on" : ""}`}
        title={item.id}
        onClick={() => setMockInput({ ...mockInput, x: item.x, y: item.y })}
      >
        {item.label}
      </button>
    );
  }
}
