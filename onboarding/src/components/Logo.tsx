/** FIFA4ALL wordmark. The "4" carries the accent colour. */

interface LogoProps {
  readonly size?: number;
  /** Accent for the "4". Override on light surfaces where lime has no contrast. */
  readonly accent?: string;
}

export function Logo({ size = 64, accent = "var(--lime)" }: LogoProps) {
  return (
    <div
      style={{
        fontFamily: "var(--display)",
        fontSize: size,
        fontWeight: 800,
        fontStyle: "italic",
        letterSpacing: "-0.03em",
        lineHeight: 1,
      }}
    >
      FIFA<span style={{ color: accent }}>4</span>ALL
    </div>
  );
}
