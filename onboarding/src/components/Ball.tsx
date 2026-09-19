/** Faceted soccer ball. Used as the nose cursor, projectile, and scene wipe. */

import "./Ball.css";

interface BallProps {
  readonly size?: number;
  readonly spin?: boolean;
}

export function Ball({ size = 32, spin = false }: BallProps) {
  return (
    <svg
      className={`ball ${spin ? "is-spinning" : ""}`}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      aria-hidden="true"
    >
      <circle cx="32" cy="32" r="30" fill="#ffffff" />
      <circle cx="32" cy="32" r="30" fill="none" stroke="#0b1424" strokeWidth="3" />
      {/* Faceted pentagon panels, kept low-poly per the brand kit. */}
      <polygon points="32,14 43,22 39,35 25,35 21,22" fill="#0b1424" />
      <polygon points="32,6 21,22 10,18 18,7" fill="#0b1424" opacity="0.72" />
      <polygon points="32,6 43,22 54,18 46,7" fill="#0b1424" opacity="0.72" />
      <polygon points="12,44 25,35 29,49 20,56" fill="#0b1424" opacity="0.72" />
      <polygon points="52,44 39,35 35,49 44,56" fill="#0b1424" opacity="0.72" />
    </svg>
  );
}
