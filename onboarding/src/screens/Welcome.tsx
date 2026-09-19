/** Screen 1 - Welcome. Sets the tone: training camp, not a settings page. */

import { Logo } from "../components/Logo";
import { Player } from "../components/Player";
import "./Welcome.css";

interface WelcomeProps {
  readonly onStart: () => void;
}

export function Welcome({ onStart }: WelcomeProps) {
  return (
    <section className="screen welcome">
      <div className="pitch-bg" />
      <div className="welcome__tunnel" />

      <div className="welcome__content">
        <p className="eyebrow">VTHacks 2026</p>
        <Logo size={92} />
        <p className="welcome__tagline">Different bodies. Same pitch.</p>
        <p className="lede">
          Play EA Sports FC with your face. No controller, no keyboard &mdash; just the movements
          you can already make.
        </p>
        <p className="welcome__prompt">Ready for training camp?</p>
        <button className="btn btn--primary" onClick={onStart} type="button">
          Start Training
          <span aria-hidden="true">&rarr;</span>
        </button>
      </div>

      {/* Team entering the pitch from the tunnel. */}
      <div className="welcome__team">
        <div className="welcome__runner welcome__runner--a">
          <Player pose="run" kit="teal" size={150} />
        </div>
        <div className="welcome__runner welcome__runner--b">
          <Player pose="run" kit="lime" size={196} skin="#8d5524" />
        </div>
        <div className="welcome__runner welcome__runner--c">
          <Player pose="idle" kit="purple" size={140} skin="#f0c9a6" />
        </div>
      </div>
    </section>
  );
}
