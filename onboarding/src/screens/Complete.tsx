/** Screen 7 - Training complete. Player card makes the controls memorable. */

import { Logo } from "../components/Logo";
import { Player } from "../components/Player";
import type { ControlChannel } from "../control/useControlState";
import "./Complete.css";

interface CompleteProps {
  readonly channel: ControlChannel;
  readonly onNext: () => void;
}

const MAPPINGS = [
  { gesture: "Head movement", action: "Run", keys: "W A S D" },
  { gesture: "Open mouth", action: "Shoot", keys: "Space" },
  { gesture: "Wink", action: "Pass", keys: "L" },
] as const;

export function Complete({ channel, onNext }: CompleteProps) {
  // Confidence reflects whether tracking is currently healthy.
  const confidence = channel.state.tracking ? 96 : 62;

  return (
    <section className="screen complete">
      <div className="pitch-bg" />
      <Confetti />

      <div className="complete__layout">
        <article className="player-card">
          <header className="player-card__head">
            <Logo size={19} accent="var(--navy-900)" />
            <span className="player-card__rating">{confidence}</span>
          </header>

          <div className="player-card__portrait">
            <Player pose="celebrate" kit="lime" size={150} />
          </div>

          <h2 className="player-card__name">Player 01</h2>

          <dl className="player-card__stats">
            {MAPPINGS.map((row) => (
              <div className="player-card__stat" key={row.gesture}>
                <dt>{row.gesture}</dt>
                <dd>
                  {row.action} <span>{row.keys}</span>
                </dd>
              </div>
            ))}
          </dl>

          <footer className="player-card__foot">
            <span>Control confidence</span>
            <strong>{confidence}%</strong>
          </footer>
        </article>

        <div className="complete__copy">
          <p className="eyebrow">Training camp</p>
          <h1 className="complete__title">Training complete</h1>
          <p className="lede">
            You&rsquo;re ready for the pitch. Your controls are locked in and will stay visible on
            this screen while you play.
          </p>
          <p className="complete__tagline">Different bodies. Same pitch.</p>
          <button className="btn btn--primary" onClick={onNext} type="button">
            Ready for Kickoff
            <span aria-hidden="true">&rarr;</span>
          </button>
        </div>
      </div>
    </section>
  );
}

/** Football-geometry confetti, generated once per mount. */
function Confetti() {
  const pieces = Array.from({ length: 34 }, (_, index) => ({
    id: index,
    left: (index * 37) % 100,
    delay: (index % 11) * 0.17,
    duration: 2.4 + ((index * 7) % 18) / 10,
    tone: ["var(--lime)", "var(--teal)", "var(--amber)", "var(--purple)"][index % 4],
    round: index % 3 === 0,
  }));

  return (
    <div className="confetti" aria-hidden="true">
      {pieces.map((piece) => (
        <span
          key={piece.id}
          className={`confetti__bit ${piece.round ? "is-round" : ""}`}
          style={{
            left: `${piece.left}%`,
            background: piece.tone,
            animationDelay: `${piece.delay}s`,
            animationDuration: `${piece.duration}s`,
          }}
        />
      ))}
    </div>
  );
}
