/** Screen 2 - How controls work. Teaches through motion, not copy. */

import { useEffect, useState } from "react";

import { IconBadge, MoveIcon, PassIcon, ShootIcon, ArrowIcon } from "../components/icons";
import type { IconTone } from "../components/icons";
import "./Controls.css";

interface ControlsProps {
  readonly onNext: () => void;
}

interface Card {
  readonly id: string;
  readonly tone: IconTone;
  readonly title: string;
  readonly gesture: string;
  readonly keys: string;
  readonly Icon: typeof MoveIcon;
}

const CARDS: readonly Card[] = [
  { id: "move", tone: "lime", title: "Move", gesture: "Head movement", keys: "W A S D", Icon: MoveIcon },
  { id: "shoot", tone: "amber", title: "Shoot", gesture: "Open mouth", keys: "Space", Icon: ShootIcon },
  { id: "pass", tone: "purple", title: "Pass", gesture: "Wink", keys: "L", Icon: PassIcon },
];

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
            <div className="control-card__art">
              <IconBadge tone={card.tone} size={92} active={step === index}>
                <card.Icon size={48} active={step === index} />
              </IconBadge>
            </div>
            <h2 className="control-card__title">{card.title}</h2>
            <p className="control-card__gesture">{card.gesture}</p>
            <span className="control-card__keys">{card.keys}</span>
          </article>
        ))}
      </div>

      <footer className="controls__footer">
        <button className="btn btn--primary" onClick={onNext} type="button">
          Let&rsquo;s Practice
          <ArrowIcon />
        </button>
      </footer>
    </section>
  );
}

