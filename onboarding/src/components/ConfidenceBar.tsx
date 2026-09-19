/** Meter showing progress toward a gesture's trigger threshold. */

import "./ConfidenceBar.css";

interface ConfidenceBarProps {
  readonly label: string;
  readonly value: number;
  readonly active: boolean;
  readonly tone?: "lime" | "teal" | "purple" | "amber";
}

export function ConfidenceBar({ label, value, active, tone = "lime" }: ConfidenceBarProps) {
  const percent = Math.round(Math.max(0, Math.min(value, 1)) * 100);
  return (
    <div className={`meter meter--${tone} ${active ? "is-active" : ""}`}>
      <div className="meter__row">
        <span className="meter__label">{label}</span>
        <span className="meter__value">{percent}%</span>
      </div>
      <div
        className="meter__track"
        role="progressbar"
        aria-label={label}
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="meter__fill" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
