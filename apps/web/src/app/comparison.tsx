import { type Comparison, formatMoney } from "@/lib/price-check";

/**
 * Cross-merchant offers for the same product (from Google Shopping data).
 * Renders nothing when there are no matched offers.
 */
export function ComparisonBlock({ comparison }: { comparison: Comparison | null }) {
  if (!comparison || comparison.offers.length === 0) return null;
  const { offers, cheapest, currency } = comparison;

  return (
    <section className="compare">
      {cheapest ? (
        <p className="compare-lead">
          Cheaper at <strong>{cheapest.merchant}</strong>:{" "}
          <span className="compare-lead-price">
            {formatMoney(cheapest.price_cents, cheapest.currency || currency)}
          </span>
        </p>
      ) : (
        <p className="compare-lead compare-lead-muted">
          Amazon.ca has the best price of the retailers we could match.
        </p>
      )}

      <ul className="compare-list">
        {offers.map((o) => (
          <li key={o.merchant}>
            <span className="compare-merchant">{o.merchant}</span>
            <span className="compare-price">
              {formatMoney(o.price_cents, o.currency || currency)}
            </span>
            {o.url ? (
              <a
                className="compare-link"
                href={o.url}
                rel="sponsored noreferrer"
                target="_blank"
              >
                View
              </a>
            ) : null}
          </li>
        ))}
      </ul>
      <p className="compare-note">
        Prices from Google Shopping, matched by product name — confirm the model
        before you buy.
      </p>
    </section>
  );
}
