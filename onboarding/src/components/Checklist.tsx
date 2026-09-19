/** Drill progress checklist with a sports-style tick animation. */

import "./Checklist.css";

export interface ChecklistItem {
  readonly id: string;
  readonly label: string;
  readonly done: boolean;
  /** Highlighted as the step the user should attempt next. */
  readonly active?: boolean;
}

interface ChecklistProps {
  readonly title: string;
  readonly items: readonly ChecklistItem[];
}

export function Checklist({ title, items }: ChecklistProps) {
  return (
    <div className="checklist panel">
      <h3 className="checklist__title">{title}</h3>
      <ul className="checklist__list">
        {items.map((item) => (
          <li
            key={item.id}
            className={`checklist__item ${item.done ? "is-done" : ""} ${
              item.active === true ? "is-active" : ""
            }`}
          >
            <span className="checklist__label">{item.label}</span>
            <span className="checklist__mark" aria-hidden="true">
              {item.done && (
                <svg viewBox="0 0 24 24" width="15" height="15">
                  <path
                    d="M4 12.5 L9.5 18 L20 6"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
            </span>
            <span className="sr-only">{item.done ? "complete" : "not complete"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
