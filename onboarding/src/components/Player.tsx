/**
 * Low-poly footballer built from flat faceted polygons.
 *
 * TECHNICAL_SPEC lists the animation states the character must expose. Each one
 * is a CSS class on the same SVG, so switching pose never remounts the figure
 * and animation timing stays decoupled from the control pipeline.
 */

import "./Player.css";

export type PlayerPose = "idle" | "run" | "shoot" | "pass" | "receive" | "celebrate";

export type PlayerKit = "lime" | "teal" | "purple" | "amber";

const KITS: Record<PlayerKit, { shirt: string; shirtDark: string; shorts: string }> = {
  lime: { shirt: "#9bff3c", shirtDark: "#6fcc22", shorts: "#0b1424" },
  teal: { shirt: "#2dd4bf", shirtDark: "#1b9e8f", shorts: "#0b1424" },
  purple: { shirt: "#a78bfa", shirtDark: "#7c5cf0", shorts: "#1d2c47" },
  amber: { shirt: "#ffb020", shirtDark: "#d88c07", shorts: "#0b1424" },
};

interface PlayerProps {
  readonly pose?: PlayerPose;
  readonly kit?: PlayerKit;
  readonly size?: number;
  /** Compass direction the player turns to face, for the movement drill. */
  readonly facing?: "N" | "NE" | "E" | "SE" | "S" | "SW" | "W" | "NW" | null;
  readonly skin?: string;
}

/** Yaw applied to the figure so it reads as turning toward the direction. */
const FACING_ROTATION: Record<string, number> = {
  N: 0, NE: 30, E: 55, SE: 30, S: 0, SW: -30, W: -55, NW: -30,
};

export function Player({
  pose = "idle",
  kit = "lime",
  size = 220,
  facing = null,
  skin = "#e8b08a",
}: PlayerProps) {
  const colors = KITS[kit];
  const yaw = facing === null ? 0 : (FACING_ROTATION[facing] ?? 0);
  // Facing south means turning toward the viewer; scale flips the shoulders.
  const lean = facing === "S" ? 1 : facing === "N" ? -1 : 0;

  return (
    <svg
      className={`player player--${pose}`}
      width={size}
      height={size * 1.35}
      viewBox="0 0 120 162"
      aria-hidden="true"
      style={{ ["--yaw" as string]: `${yaw}deg`, ["--lean" as string]: `${lean * 6}deg` }}
    >
      {/* Long soft cast shadow, allowed by the brand kit. */}
      <ellipse className="player__shadow" cx="60" cy="152" rx="34" ry="7" />

      <g className="player__body">
        {/* Back leg */}
        <g className="player__leg player__leg--back">
          <polygon points="56,96 66,96 64,124 54,124" fill={colors.shorts} />
          <polygon points="54,124 64,124 62,144 52,144" fill={skin} />
          <polygon points="50,144 64,142 65,150 48,150" fill="#0b1424" />
        </g>

        {/* Front leg */}
        <g className="player__leg player__leg--front">
          <polygon points="54,96 64,96 62,124 52,124" fill={colors.shorts} />
          <polygon points="52,124 62,124 60,144 50,144" fill={skin} />
          <polygon points="46,144 60,142 61,150 44,150" fill="#f2f6fb" />
        </g>

        {/* Torso, faceted into two tones for the low-poly read */}
        <polygon points="42,52 78,52 74,98 46,98" fill={colors.shirt} />
        <polygon points="60,52 78,52 74,98 60,98" fill={colors.shirtDark} />
        <polygon points="46,98 74,98 72,104 48,104" fill={colors.shorts} />

        {/* Arms */}
        <g className="player__arm player__arm--back">
          <polygon points="42,54 50,56 44,86 36,84" fill={colors.shirtDark} />
          <polygon points="36,84 44,86 42,98 34,96" fill={skin} />
        </g>
        <g className="player__arm player__arm--front">
          <polygon points="70,56 78,54 84,84 76,86" fill={colors.shirt} />
          <polygon points="76,86 84,84 86,96 78,98" fill={skin} />
        </g>

        {/* Head: minimal facial detail, strong silhouette */}
        <g className="player__head">
          <polygon points="52,22 68,22 71,38 60,46 49,38" fill={skin} />
          <polygon points="60,22 68,22 71,38 60,46" fill="#d69a73" />
          <polygon points="49,20 71,20 69,14 51,14" fill="#2a1a12" />
          <polygon points="52,52 68,52 66,46 54,46" fill={skin} />
        </g>
      </g>
    </svg>
  );
}
