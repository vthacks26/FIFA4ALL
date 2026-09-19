/** Small hooks shared by the drill screens. */

import { useEffect, useRef, useState } from "react";

/**
 * Run a callback once per rising edge of a gesture.
 *
 * The bridge already edge-triggers, but mock mode and reconnects can repeat a
 * frame, so the latch is enforced here too.
 */
export function useGestureEdge(active: boolean, onFire: () => void): void {
  const wasActive = useRef(false);
  const handler = useRef(onFire);
  handler.current = onFire;

  useEffect(() => {
    if (active && !wasActive.current) handler.current();
    wasActive.current = active;
  }, [active]);
}

/**
 * Track how long a condition has held, in seconds, resetting when it breaks.
 * Used for the calibration dwell and the movement drill hold.
 */
export function useHoldProgress(active: boolean, seconds: number): number {
  const [progress, setProgress] = useState(0);
  const startedAt = useRef<number | null>(null);

  useEffect(() => {
    if (!active) {
      startedAt.current = null;
      setProgress(0);
      return;
    }
    let frame = 0;
    const tick = () => {
      const now = performance.now();
      startedAt.current ??= now;
      const elapsed = (now - startedAt.current) / 1000;
      setProgress(Math.min(elapsed / seconds, 1));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [active, seconds]);

  return progress;
}

/** Persist orientation progress so a refresh does not restart the sequence. */
export function usePersistentState<T>(key: string, initial: T): [T, (next: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = window.localStorage.getItem(key);
      return stored === null ? initial : (JSON.parse(stored) as T);
    } catch {
      return initial;
    }
  });

  const update = (next: T) => {
    setValue(next);
    try {
      window.localStorage.setItem(key, JSON.stringify(next));
    } catch {
      // Storage can be unavailable in private mode; progress is not critical.
    }
  };

  return [value, update];
}
