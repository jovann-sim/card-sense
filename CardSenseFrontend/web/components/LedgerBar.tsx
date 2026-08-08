import type { CSSProperties } from "react";
import { money } from "@/lib/format";

/**
 * The page's signature. Solid verdigris is reward already banked; hatched
 * brass is reward the optimal card would have earned instead. The same bar
 * runs full-width in the hero and 10px tall on every category row, so the
 * two scales read as one statement.
 */
export function LedgerBar({
  captured,
  unclaimed,
  variant,
  delay = 0,
  label,
}: {
  captured: number;
  unclaimed: number;
  variant: "hero" | "row";
  delay?: number;
  label: string;
}) {
  const total = captured + unclaimed;
  const capturedPct = total === 0 ? 0 : (captured / total) * 100;

  return (
    <div className={`bar bar--${variant}`} role="img" aria-label={label}>
      <div
        className="bar__seg bar__seg--captured"
        style={{ "--w": `${capturedPct}%`, "--delay": `${delay}ms` } as CSSProperties}
      />
      <div
        className="bar__seg bar__seg--unclaimed"
        style={
          { "--w": `${100 - capturedPct}%`, "--delay": `${delay}ms` } as CSSProperties
        }
      />
    </div>
  );
}

export function LedgerLegend({
  captured,
  unclaimed,
}: {
  captured: number;
  unclaimed: number;
}) {
  return (
    <div className="legend">
      <p className="legend__item">
        <span className="legend__swatch legend__swatch--captured" aria-hidden />
        <span className="legend__value">{money(captured)}</span>
        <span className="legend__label">banked</span>
      </p>
      <p className="legend__item">
        <span className="legend__swatch legend__swatch--unclaimed" aria-hidden />
        <span className="legend__value">{money(unclaimed)}</span>
        <span className="legend__label">left on the table</span>
      </p>
    </div>
  );
}
