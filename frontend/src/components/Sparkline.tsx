interface SparklineProps {
  data: number[];
  /** CSS color (token) for the line, fill and endpoint. */
  color?: string;
  width?: number;
  height?: number;
  /** Fix the vertical domain; defaults to the data's own min/max. */
  min?: number;
  max?: number;
  ariaLabel?: string;
}

/**
 * Minimal streaming trend line — thin stroke, faint area, emphasized endpoint.
 * Pure SVG, no animation (reduced-motion safe). Renders a flat baseline until
 * at least two samples are buffered.
 */
export default function Sparkline({
  data,
  color = "var(--cyan)",
  width = 68,
  height = 20,
  min,
  max,
  ariaLabel,
}: SparklineProps) {
  const pad = 2;
  const w = width - pad * 2;
  const h = height - pad * 2;

  if (!data || data.length < 2) {
    return (
      <svg className="spark" width={width} height={height} aria-hidden="true">
        <line
          x1={pad}
          y1={height / 2}
          x2={width - pad}
          y2={height / 2}
          stroke="var(--line-strong)"
          strokeWidth="1"
        />
      </svg>
    );
  }

  const lo = min ?? Math.min(...data);
  const hi = max ?? Math.max(...data);
  const span = hi - lo || 1;

  const points = data.map((value, index) => {
    const x = pad + (index / (data.length - 1)) * w;
    const y = pad + h - ((value - lo) / span) * h;
    return [x, y] as const;
  });

  const line = points
    .map(([x, y], index) => `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`)
    .join(" ");
  const area = `${line} L${(pad + w).toFixed(1)} ${(pad + h).toFixed(1)} L${pad} ${(pad + h).toFixed(1)} Z`;
  const [endX, endY] = points[points.length - 1];

  return (
    <svg
      className="spark"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={ariaLabel}
      style={{ color }}
    >
      <path d={area} fill="currentColor" opacity="0.12" />
      <path
        d={line}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={endX} cy={endY} r="2.1" fill="currentColor" />
    </svg>
  );
}
