/** Screen 2 - How controls work. Teaches through motion, not copy. */

import { useEffect, useState } from "react";

import { Ball } from "../components/Ball";
import { Player } from "../components/Player";
import "./Controls.css";

interface ControlsProps {
  readonly onNext: () => void;
}

const CARDS = [
  {
    id: "move",
    tone: "lime",
    title: "Move",
    gesture: "Head movement",
    keys: "W A S D",
  },
  {
    id: "shoot",
    tone: "amber",
    title: "Shoot",
    gesture: "Open mouth",
    keys: "Space",
  },
  {
    id: "pass",
    tone: "purple",
    title: "Pass",
    gesture: "Wink",
    keys: "L",
  },
] as const;

export function Controls({ onNext }: ControlsProps) {
  // Each control animates in sequence, then the demo loops.
  const [step, setStep] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => setStep((current) => (current + 1) % 3), 2200);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <section className="screen controls">
      <div className="pitch-bg" />

      <header className="controls__header">
        <p className="eyebrow">How it works</p>
        <h1 className="controls__title">
          Control the pitch
          <br />
          with your face
        </h1>
        <p className="lede">Three movements. That is the whole controller.</p>
      </header>

      <div className="controls__cards">
        {CARDS.map((card, index) => (
          <article
            key={card.id}
            className={`control-card control-card--${card.tone} ${step === index ? "is-active" : ""}`}
            style={{ animationDelay: `${index * 0.14}s` }}
          >
            <div className="control-card__art">{renderArt(card.id, step === index)}</div>
            <h2 className="control-card__title">{card.title}</h2>
            <p className="control-card__gesture">{card.gesture}</p>
            <span className="control-card__keys">{card.keys}</span>
          </article>
        ))}
      </div>

      <footer className="controls__footer">
        <button className="btn btn--primary" onClick={onNext} type="button">
          Let&rsquo;s Practice
          <span aria-hidden="true">&rarr;</span>
        </button>
      </footer>
    </section>
  );
}

function renderArt(id: (typeof CARDS)[number]["id"], active: boolean) {
  if (id === "move") {
    return (
      <div className={`art art--move ${active ? "is-playing" : ""}`}>
        <div className="art__ring" />
        <div className="art__orbit">
          <Ball size={26} spin={active} />
        </div>
      </div>
    );
  }
  if (id === "shoot") {
    return (
      <div className={`art art--shoot ${active ? "is-playing" : ""}`}>
        <Player pose={active ? "shoot" : "idle"} kit="amber" size={92} />
        <div className="art__shot">
          <Ball size={20} spin={active} />
        </div>
      </div>
    );
  }
  return (
    <div className={`art art--pass ${active ? "is-playing" : ""}`}>
      <Player pose={active ? "pass" : "idle"} kit="purple" size={80} />
      <div className="art__pass-ball">
        <Ball size={18} spin={active} />
      </div>
      <Player pose={active ? "receive" : "idle"} kit="teal" size={72} skin="#8d5524" />
    </div>
  );
}
