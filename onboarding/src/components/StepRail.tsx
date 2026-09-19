/**
 * Where you are in training.
 *
 * Nine screens with no orientation is disorienting for a first-time user, and
 * a judge watching over a shoulder cannot tell how much is left. The rail
 * names the three drills and marks them done as they pass.
 */

import type { Phase } from "../types";
import "./StepRail.css";

interface Step {
  readonly id: string;
  readonly label: string;
  readonly phases: readonly Phase[];
}

const STEPS: readonly Step[] = [
  { id: "setup", label: "Setup", phases: ["CENTER_CALIBRATION"] },
  { id: "move", label: "Move", phases: ["MOVEMENT_TRAINING"] },
  { id: "shoot", label: "Shoot", phases: ["SHOOTING_TRAINING"] },
  { id: "pass", label: "Pass", phases: ["PASSING_TRAINING"] },
];

/** Order used to decide which steps are already behind the user. */
const SEQUENCE: readonly Phase[] = [
  "CENTER_CALIBRATION",
  "MOVEMENT_TRAINING",
  "SHOOTING_TRAINING",
  "PASSING_TRAINING",
];

interface StepRailProps {
  readonly phase: Phase;
}

export function StepRail({ phase }: StepRailProps) {
  const position = SEQUENCE.indexOf(phase);
  if (position < 0) return null;

  return (
    <ol className="rail" aria-label="Training progress">
      {STEPS.map((step, index) => {
        const done = index < position;
        const active = index === position;
        return (
          <li
            key={step.id}
            className={`rail__step ${done ? "is-done" : ""} ${active ? "is-active" : ""}`}
            aria-current={active ? "step" : undefined}
          >
            <span className="rail__dot">
              {done && (
                <svg viewBox="0 0 24 24" width="11" height="11" aria-hidden="true">
                  <path
                    d="M4 12.5 L9.5 18 L20 6"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
            </span>
            <span className="rail__label">{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}
