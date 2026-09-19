/**
 * Match-mode status bar.
 *
 * During a match the two things that silently break the demo are the input
 * being disarmed and the game losing keyboard focus. Both look identical to
 * broken tracking from the outside, so both get stated plainly here.
 */

import type { ControlState } from "../types";
import "./MatchStatus.css";

interface MatchStatusProps {
  readonly state: ControlState;
  readonly onArm: (next: boolean) => void;
  readonly keyboardProblem?: string | null;
  readonly disabled?: boolean;
}

export function MatchStatus({
  state,
  onArm,
  keyboardProblem,
  disabled = false,
}: MatchStatusProps) {
  const armed = state.armed === true;
  // Focus only matters once we are actually sending keys.
  const focusLost = armed && state.game_focus === false;

  return (
    <div className="match">
      <button
        type="button"
        className={`match__arm ${armed ? "is-armed" : ""}`}
        onClick={() => onArm(!armed)}
        disabled={disabled || keyboardProblem != null}
      >
        <span className="match__dot" />
        {armed ? "Controls live" : "Controls off"}
      </button>

      {keyboardProblem != null && (
        <p className="match__alert match__alert--error">{keyboardProblem}</p>
      )}

      {keyboardProblem == null && focusLost && (
        <p className="match__alert match__alert--warn">
          <strong>{state.frontmost ?? "Another app"}</strong> has the keyboard. Click the
          game window on Monitor 1 &mdash; keys are not reaching it.
        </p>
      )}

      {keyboardProblem == null && !armed && (
        <p className="match__alert">
          Start the match on Monitor 1, click the game window, then turn controls on.
        </p>
      )}

      {armed && !focusLost && (
        <p className="match__alert match__alert--ok">
          Sending to <strong>{state.frontmost ?? "the focused app"}</strong>
        </p>
      )}
    </div>
  );
}
