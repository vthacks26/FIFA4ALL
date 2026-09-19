/**
 * 16-bit pixel-art footballer, drawn as an SVG pixel grid.
 *
 * Poses rotate limb groups rather than swapping images. The arms and legs are
 * separate <g> elements pivoting at shoulder and hip, so `run` is a genuine
 * counter-phased stride and `shoot` is a leg that winds up and strikes through.
 * That is how this component worked before rendered PNG frames replaced it; the
 * articulation is restored here, and the pixel styling is new.
 *
 * The figure is authored on a 32x46 integer grid and drawn with
 * `shape-rendering: crispEdges`, so it stays hard-edged at any size. The whole
 * six-kit cast is a few KB of markup instead of ten megabytes of sprite sheets,
 * and adding a kit is three colour values.
 */

import "./Player.css";

export type PlayerPose =
  "idle" | "run" | "shoot" | "pass" | "receive" | "celebrate";

/** Each kit is a distinct character on the pitch. */
export type PlayerKit =
  "lime" | "teal" | "purple" | "amber" | "crimson" | "slate";

export type Facing = "N" | "NE" | "E" | "SE" | "S" | "SW" | "W" | "NW";

interface Kit {
  readonly shirt: string;
  /** Hoops, collar, sleeve cuffs and socks. */
  readonly trim: string;
  readonly shorts: string;
}

const KITS: Record<PlayerKit, Kit> = {
  lime: { shirt: "#9bff3c", trim: "#4f9418", shorts: "#12203a" },
  teal: { shirt: "#2dd4bf", trim: "#13705f", shorts: "#0b1424" },
  purple: { shirt: "#a78bfa", trim: "#5f3ad4", shorts: "#1d2c47" },
  amber: { shirt: "#ffb020", trim: "#a85f00", shorts: "#12203a" },
  crimson: { shirt: "#ff4d5e", trim: "#9c1128", shorts: "#12203a" },
  slate: { shirt: "#9fb3c8", trim: "#42556d", shorts: "#0b1424" },
};

const SKIN = "#e8b08a";
/** Limbs on the far side of the body, and shaded facets on the near side. */
const SKIN_SHADE = "#c98d68";
const HAIR = "#35211a";
const INK = "#15100e";
const BOOT = "#f2f6fb";

/** Running away from the camera shows the back of the head. */
const AWAY: ReadonlySet<Facing> = new Set<Facing>(["N", "NE", "NW"]);

/** A small yaw sells the turn without distorting the pixel grid. */
const YAW: Record<Facing, number> = {
  N: 0,
  S: 0,
  NE: 26,
  SE: 26,
  E: 48,
  NW: -26,
  SW: -26,
  W: -48,
};

/** One block on the sprite grid. */
function Px(props: { x: number; y: number; w?: number; h?: number; fill: string }) {
  const { x, y, w = 1, h = 1, fill } = props;
  return <rect x={x} y={y} width={w} height={h} fill={fill} />;
}

/** Thigh, sock and boot. `x` is the leg's left edge, `toeX` the boot's toe.
 *  The top two rows are shorts-coloured so the hip pivot sits inside the
 *  shorts: rotating about an exposed top edge swings a visible notch out from
 *  under the body on every stride. */
function Leg({ x, kit, toeX, far = false }: {
  x: number; kit: Kit; toeX: number; far?: boolean;
}) {
  const skin = far ? SKIN_SHADE : SKIN;
  return (
    <>
      <Px x={x} y={31} w={4} h={2} fill={kit.shorts} />
      <Px x={x} y={33} w={4} h={6} fill={skin} />
      <Px x={x} y={39} w={4} h={3} fill={kit.trim} />
      <Px x={x} y={42} w={4} h={2} fill={BOOT} />
      <Px x={toeX} y={42} w={1} h={2} fill={BOOT} />
      <Px x={x} y={43} w={4} h={1} fill={INK} />
      <Px x={toeX} y={43} w={1} h={1} fill={INK} />
    </>
  );
}

/** Sleeve, forearm and hand. `x` is the arm's left edge. */
function Arm({ x, sleeve, skin }: { x: number; sleeve: string; skin: string }) {
  return (
    <>
      <Px x={x} y={14} w={3} h={6} fill={sleeve} />
      <Px x={x} y={20} w={3} h={7} fill={skin} />
    </>
  );
}

/** Facial detail is dropped on the rear view, leaving the back of the head. */
function Head({ away }: { away: boolean }) {
  return (
    <>
      <Px x={11} y={3} w={10} h={3} fill={HAIR} />
      <Px x={11} y={6} w={10} h={6} fill={away ? HAIR : SKIN} />
      {!away && (
        <>
          <Px x={12} y={6} w={8} h={1} fill={HAIR} />
          <Px x={11} y={6} w={1} h={3} fill={HAIR} />
          <Px x={20} y={6} w={1} h={3} fill={HAIR} />
          <Px x={19} y={7} w={1} h={5} fill={SKIN_SHADE} />
          <Px x={10} y={8} w={1} h={2} fill={SKIN} />
          <Px x={21} y={8} w={1} h={2} fill={SKIN} />
          <Px x={13} y={8} w={1} h={2} fill={INK} />
          <Px x={18} y={8} w={1} h={2} fill={INK} />
          <Px x={15} y={10} w={2} h={1} fill={SKIN_SHADE} />
        </>
      )}
      <Px x={14} y={12} w={4} h={2} fill={away ? SKIN_SHADE : SKIN} />
    </>
  );
}

/** Shirt and shorts. Hoops read as "football kit" faster than any other mark
 *  at this resolution. */
function Torso({ kit, away }: { kit: Kit; away: boolean }) {
  return (
    <>
      <Px x={10} y={14} w={12} h={14} fill={kit.shirt} />
      <Px x={10} y={17} w={12} h={2} fill={kit.trim} />
      <Px x={10} y={22} w={12} h={2} fill={kit.trim} />
      <Px x={13} y={14} w={6} h={1} fill={kit.trim} />
      {!away && <Px x={15} y={14} w={2} h={1} fill={SKIN} />}
      <Px x={10} y={28} w={12} h={5} fill={kit.shorts} />
      <Px x={10} y={28} w={12} h={1} fill={kit.trim} />
    </>
  );
}

interface PlayerProps {
  readonly pose?: PlayerPose;
  readonly kit?: PlayerKit;
  /** Rendered height in pixels. Width follows the sprite's 32:46 grid. */
  readonly size?: number;
  /** Compass direction the player turns to face, for the movement drill. */
  readonly facing?: Facing | null;
}

export function Player({
  pose = "idle",
  kit = "lime",
  size = 220,
  facing = null,
}: PlayerProps) {
  const colors = KITS[kit];
  const away = facing !== null && AWAY.has(facing);
  const yaw = facing === null ? 0 : YAW[facing];
  // Straight up or down tips the shoulders rather than turning them, because a
  // yaw of zero would leave N and S looking identical.
  const lean = facing === "S" ? 4 : facing === "N" ? -4 : 0;

  return (
    <svg
      className={`player player--${pose}`}
      width={(size * 32) / 46}
      height={size}
      viewBox="0 0 32 46"
      aria-hidden="true"
      style={{
        ["--yaw" as string]: `${yaw}deg`,
        ["--lean" as string]: `${lean}deg`,
      }}
    >
      <ellipse className="player__shadow" cx="16" cy="44.6" rx="9" ry="1.4" />

      <g className="player__body">
        <g className="player__limb player__arm player__arm--back">
          <Arm x={7} sleeve={colors.trim} skin={SKIN_SHADE} />
        </g>
        <g className="player__limb player__leg player__leg--back">
          <Leg x={11} kit={colors} toeX={10} far />
        </g>

        <Torso kit={colors} away={away} />
        <g className="player__head">
          <Head away={away} />
        </g>

        <g className="player__limb player__leg player__leg--front">
          <Leg x={17} kit={colors} toeX={21} />
        </g>
        <g className="player__limb player__arm player__arm--front">
          <Arm x={22} sleeve={colors.shirt} skin={SKIN} />
        </g>

        {/* Shoulder caps. These do not rotate, so neither sleeve's pivot corner
            can swing out above the shirt line mid-stride. */}
        <Px x={7} y={14} w={3} h={2} fill={colors.trim} />
        <Px x={22} y={14} w={3} h={2} fill={colors.shirt} />
      </g>
    </svg>
  );
}
