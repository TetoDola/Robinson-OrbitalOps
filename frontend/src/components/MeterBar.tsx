interface MeterZone {
  /** Fill tone applies when value <= upTo (zones checked in order). */
  upTo: number;
  tone: string;
}

interface MeterBarProps {
  value: number;
  max: number;
  min?: number;
  /** Optional reference marker (reserve / required threshold). */
  target?: number;
  /** Threshold-driven fill color; first matching zone wins. */
  zones?: MeterZone[];
  /** Fill color when no zones are supplied. */
  tone?: string;
  ariaLabel?: string;
}

/**
 * Horizontal bullet / meter: a value bar within a [min, max] range, colored by
 * threshold zone, with an optional target marker. The numeric value is rendered
 * by the caller as text (never rely on bar length alone).
 */
export default function MeterBar({
  value,
  max,
  min = 0,
  target,
  zones,
  tone = "var(--cyan)",
  ariaLabel,
}: MeterBarProps) {
  const span = max - min || 1;
  const pct = Math.max(0, Math.min(1, (value - min) / span));
  const fill = zones
    ? zones.find((zone) => value <= zone.upTo)?.tone ?? zones[zones.length - 1].tone
    : tone;
  const targetPct =
    target != null ? Math.max(0, Math.min(1, (target - min) / span)) : null;

  return (
    <div
      className="meter"
      role="meter"
      aria-valuenow={Math.round(value)}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-label={ariaLabel}
    >
      <div className="meter-track">
        <div className="meter-fill" style={{ width: `${pct * 100}%`, background: fill }} />
      </div>
      {targetPct != null && (
        <span className="meter-target" style={{ left: `${targetPct * 100}%` }} aria-hidden="true" />
      )}
    </div>
  );
}
