/**
 * Screen 8 - Transition to game.
 *
 * The ball rockets toward the camera and fills the screen, becoming the wipe
 * into live mode. The main monitor is already on EA Sports FC via Luna.
 */

import { useEffect, useRef } from "react";

import { Ball } from "../components/Ball";
import "./Transition.css";

const DURATION_MS = 2100;

interface TransitionProps {
  readonly onDone: () => void;
}

export function Transition({ onDone }: TransitionProps) {
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  useEffect(() => {
    const timer = window.setTimeout(() => doneRef.current(), DURATION_MS);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <section className="screen transition">
      <div className="pitch-bg" />
      <div className="transition__speed" />

      <div className="transition__ball">
        <Ball size={220} spin />
      </div>

      <p className="transition__copy">Let&rsquo;s play.</p>

      <button className="btn btn--ghost transition__skip" onClick={onDone} type="button">
        Skip
      </button>
    </section>
  );
}
