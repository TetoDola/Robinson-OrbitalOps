interface RadialGaugeProps {
  value: number;
  max?: number;
  tone?: string;
  label: string;
  sub?: string;
  size?: number;
}

/** FUI ring gauge — a value arc with soft glow, value shown as text in the centre. */
export default function RadialGauge({
  value,
  max = 100,
  tone = "var(--accent)",
  label,
  sub,
  size = 74,
}: RadialGaugeProps) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="rgauge">
      <svg viewBox="0 0 100 100" width={size} height={size} aria-hidden="true">
        <circle className="rg-track" cx="50" cy="50" r="42" fill="none" strokeWidth="7" />
        <circle
          className="rg-val"
          cx="50"
          cy="50"
          r="42"
          fill="none"
          strokeWidth="7"
          strokeLinecap="round"
          pathLength={100}
          strokeDasharray={`${pct} 100`}
          transform="rotate(-90 50 50)"
          style={{ stroke: tone }}
        />
      </svg>
      <div className="rg-num">
        {label}
        {sub ? <small>{sub}</small> : null}
      </div>
    </div>
  );
}
