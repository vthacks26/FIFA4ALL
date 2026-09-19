/**
 * Low-poly footballer.
 *
 * These are the reference renders supplied with the brief, cut out of
 * `assets/low-poly-reference-{front,back}.png` by `tools/extract_players.py`.
 * Hand-drawn SVG polygons were never going to match a 3D render: the faceted
 * shading, kit detail and proportions are the whole look, and approximating
 * them by hand produced a paper doll.
 *
 * The trade is articulation. A sprite cannot swing its own legs, so the poses
 * TECHNICAL_SPEC asks for are built from whole-figure motion: weight shifts,
 * leans, bounce and squash. Read against a moving ball and a reacting net that
 * carries the action, and it keeps animation timing fully decoupled from the
 * control pipeline.
 */

import "./Player.css";

export type PlayerPose = "idle" | "run" | "shoot" | "pass" | "receive" | "celebrate";

/** Each kit is a distinct character from the reference sheet. */
export type PlayerKit = "lime" | "teal" | "purple" | "amber" | "crimson" | "slate";

const SPRITE_INDEX: Record<PlayerKit, number> = {
  crimson: 1,
  lime: 2,
  amber: 3,
  slate: 4,
  teal: 5,
  purple: 6,
};

export type Facing = "N" | "NE" | "E" | "SE" | "S" | "SW" | "W" | "NW";

interface PlayerProps {
  readonly pose?: PlayerPose;
  readonly kit?: PlayerKit;
  /** Rendered height in pixels. Sprites vary in width, so height is what
   *  layouts can actually reason about. */
  readonly size?: number;
  /** Compass direction the player turns to face, for the movement drill. */
  readonly facing?: Facing | null;
}

/** Running away from the camera shows the player's back. */
const AWAY: ReadonlySet<Facing> = new Set<Facing>(["N", "NE", "NW"]);
/** Facing the player's own left reads as a mirrored sprite. */
const MIRRORED: ReadonlySet<Facing> = new Set<Facing>(["W", "NW", "SW"]);

/** A small yaw sells the turn without distorting the figure. */
const YAW: Record<Facing, number> = {
  N: 0, S: 0, NE: 12, SE: 12, E: 20, NW: -12, SW: -12, W: -20,
};

export function Player({ pose = "idle", kit = "lime", size = 220, facing = null }: PlayerProps) {
  const view = facing !== null && AWAY.has(facing) ? "back" : "front";
  const mirrored = facing !== null && MIRRORED.has(facing);
  const yaw = facing === null ? 0 : YAW[facing];

  return (
    <div
      className={`player player--${pose} ${mirrored ? "is-mirrored" : ""}`}
      style={{ height: size, ["--yaw" as string]: `${yaw}deg` }}
      aria-hidden="true"
    >
      <img
        className="player__sprite"
        src={`${import.meta.env.BASE_URL}players/${view}-${SPRITE_INDEX[kit]}.png`}
        alt=""
        draggable={false}
      />
    </div>
  );
}
