/**
 * Low-poly footballer.
 *
 * Every pose is its own rendered frame. The previous sprites had only a front
 * and a back view, so `run`, `shoot` and `pass` were the same standing figure
 * under a CSS transform — the legs never moved, and no amount of bounce hid it.
 *
 * Running is the case that needs two frames rather than one. A single stride
 * held still reads as a man frozen mid-air being slid across the grass, so each
 * kit carries two opposite phases of the stride and CSS alternates them. The
 * rest of the motion (bob, lean, squash) still rides on top, but it is now
 * decoration over real articulation instead of a substitute for it.
 */

import "./Player.css";

export type PlayerPose =
  "idle" | "run" | "shoot" | "pass" | "receive" | "celebrate";

/** Each kit is a distinct character, generated as a matched set of poses. */
export type PlayerKit =
  "lime" | "teal" | "purple" | "amber" | "crimson" | "slate";

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
  N: 0,
  S: 0,
  NE: 12,
  SE: 12,
  E: 20,
  NW: -12,
  SW: -12,
  W: -20,
};

/**
 * Receiving is a player waiting on the ball, which is the idle stance. It has
 * no frame of its own rather than a near-duplicate of one.
 */
const FRAME_FOR_POSE: Record<PlayerPose, string> = {
  idle: "idle",
  run: "run",
  shoot: "shoot",
  pass: "pass",
  receive: "idle",
  celebrate: "celebrate",
};

function spriteUrl(kit: PlayerKit, frame: string): string {
  return `${import.meta.env.BASE_URL}players/${kit}-${frame}.png`;
}

export function Player({
  pose = "idle",
  kit = "lime",
  size = 220,
  facing = null,
}: PlayerProps) {
  const away = facing !== null && AWAY.has(facing);
  const mirrored = facing !== null && MIRRORED.has(facing);
  const yaw = facing === null ? 0 : YAW[facing];

  // Turning upfield shows the back, which only exists as a standing frame.
  const frame = away ? "back" : FRAME_FOR_POSE[pose];
  const running = pose === "run" && !away;

  return (
    <div
      className={`player player--${pose} ${mirrored ? "is-mirrored" : ""}`}
      style={{ height: size, ["--yaw" as string]: `${yaw}deg` }}
      aria-hidden="true"
    >
      {running ? (
        <>
          <img
            className="player__sprite player__sprite--stride-a"
            src={spriteUrl(kit, "run")}
            alt=""
            draggable={false}
          />
          <img
            className="player__sprite player__sprite--stride-b"
            src={spriteUrl(kit, "runb")}
            alt=""
            draggable={false}
          />
        </>
      ) : (
        <img
          className="player__sprite"
          src={spriteUrl(kit, frame)}
          alt=""
          draggable={false}
        />
      )}
    </div>
  );
}
