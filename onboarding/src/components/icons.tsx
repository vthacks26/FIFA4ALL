/**
 * Icon set for the three FIFA4ALL controls.
 *
 * Drawn rather than pulled from a library: an open mouth has no equivalent in
 * general icon sets, and a generic stroke set would read as SaaS next to the
 * low-poly players. One geometry, one stroke weight, so the three sit together
 * as a system. Each takes `active` so the icon itself performs the gesture it
 * describes, which is what teaches it.
 */

import "./icons.css";

export type IconTone = "lime" | "amber" | "purple" | "teal";

interface IconProps {
  readonly size?: number;
  readonly active?: boolean;
}

const VIEW_BOX = "0 0 32 32";

/** Head movement: four arrows from a centre point. */
export function MoveIcon({ size = 32, active = false }: IconProps) {
  return (
    <svg
      className={`icon icon--move ${active ? "is-active" : ""}`}
      width={size}
      height={size}
      viewBox={VIEW_BOX}
      fill="none"
      aria-hidden="true"
    >
      <g className="icon__arrow icon__arrow--n">
        <path d="M16 13 V4" />
        <path d="M12 8 L16 4 L20 8" />
      </g>
      <g className="icon__arrow icon__arrow--s">
        <path d="M16 19 V28" />
        <path d="M12 24 L16 28 L20 24" />
      </g>
      <g className="icon__arrow icon__arrow--w">
        <path d="M13 16 H4" />
        <path d="M8 12 L4 16 L8 20" />
      </g>
      <g className="icon__arrow icon__arrow--e">
        <path d="M19 16 H28" />
        <path d="M24 12 L28 16 L24 20" />
      </g>
      <circle className="icon__dot" cx="16" cy="16" r="2.4" />
    </svg>
  );
}

/** Open mouth: two lips that part when the gesture fires. */
export function ShootIcon({ size = 32, active = false }: IconProps) {
  return (
    <svg
      className={`icon icon--shoot ${active ? "is-active" : ""}`}
      width={size}
      height={size}
      viewBox={VIEW_BOX}
      fill="none"
      aria-hidden="true"
    >
      <g className="icon__mouth">
        <ellipse className="icon__mouth-open" cx="16" cy="17" rx="7" ry="9" />
        <path className="icon__lip icon__lip--upper" d="M7 12 Q11.5 7.5 16 11 Q20.5 7.5 25 12" />
        <path className="icon__lip icon__lip--lower" d="M8 22 Q16 29 24 22" />
      </g>
    </svg>
  );
}

/** Wink: an eye whose lid closes when the gesture fires. */
export function PassIcon({ size = 32, active = false }: IconProps) {
  return (
    <svg
      className={`icon icon--pass ${active ? "is-active" : ""}`}
      width={size}
      height={size}
      viewBox={VIEW_BOX}
      fill="none"
      aria-hidden="true"
    >
      <path className="icon__brow" d="M6 9 Q16 3 26 9" />
      <g className="icon__eye-open">
        <path d="M2 18 Q16 9 30 18 Q16 27 2 18 Z" />
        <circle className="icon__pupil" cx="16" cy="18" r="3.4" />
      </g>
      <g className="icon__eye-shut">
        <path d="M3 16 Q16 25 29 16" />
        <path className="icon__lash" d="M8 21 L6.5 24" />
        <path className="icon__lash" d="M16 23.5 L16 26.5" />
        <path className="icon__lash" d="M24 21 L25.5 24" />
      </g>
    </svg>
  );
}

/** Arrow used on calls to action, so buttons do not rely on a text glyph. */
export function ArrowIcon({ size = 18 }: IconProps) {
  return (
    <svg
      className="icon icon--arrow"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <path d="M4 12 H19" />
      <path d="M13 6 L19 12 L13 18" />
    </svg>
  );
}

interface BadgeProps {
  readonly tone: IconTone;
  readonly size?: number;
  readonly active?: boolean;
  readonly children: React.ReactNode;
}

/** Circular tinted badge the control icons sit inside. */
export function IconBadge({ tone, size = 64, active = false, children }: BadgeProps) {
  return (
    <span
      className={`icon-badge icon-badge--${tone} ${active ? "is-active" : ""}`}
      style={{ width: size, height: size }}
    >
      {children}
    </span>
  );
}
