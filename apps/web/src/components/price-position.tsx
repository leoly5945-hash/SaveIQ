import { formatMoney, type PricePosition } from "@/lib/price-check";

/**
 * A 90-day range bar: low on the left, high on the right, a marker for today.
 * Makes "this is the highest price in 90 days" visible at a glance.
 */
export function PricePositionBar({
  position,
  currency,
}: {
  position: PricePosition;
  currency: string;
}) {
  const pct = Math.round(Math.max(0, Math.min(1, position.position)) * 100);
  return (
    <div className="price-position" role="img" aria-label={positionLabel(position, currency)}>
      <div className="price-position-track">
        <span
          className={`price-position-marker${pct < 15 ? " is-start" : pct > 85 ? " is-end" : ""}`}
          style={{ left: `${pct}%` }}
        >
          <span className="price-position-today">
            Today {formatMoney(position.current_cents, currency)}
          </span>
        </span>
      </div>
      <div className="price-position-ends" aria-hidden="true">
        <span>90-day low {formatMoney(position.low_cents, currency)}</span>
        <span>high {formatMoney(position.high_cents, currency)}</span>
      </div>
    </div>
  );
}

function positionLabel(p: PricePosition, currency: string): string {
  return `Today's price ${formatMoney(p.current_cents, currency)}, in a 90-day range from ${formatMoney(p.low_cents, currency)} to ${formatMoney(p.high_cents, currency)}.`;
}

export function DiscountChecks({
  checks,
}: {
  checks: { kind: string; warning: boolean; message: string }[];
}) {
  if (checks.length === 0) return null;
  return (
    <section className="discount-checks" aria-label="Is the discount real?">
      <p className="discount-checks-title">Is the discount real?</p>
      <ul>
        {checks.map((check) => (
          <li
            className={check.warning ? "discount-check is-warning" : "discount-check is-ok"}
            key={check.kind}
          >
            <span aria-hidden="true" className="discount-check-mark">
              {check.warning ? "!" : "✓"}
            </span>
            <span>{check.message}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
