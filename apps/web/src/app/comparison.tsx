import { type Comparison, formatMoney } from "@/lib/price-check";

/**
 * Cross-merchant offers for the same product (from Google Shopping data).
 * Renders nothing when there are no matched offers.
 */
export function ComparisonBlock({ comparison }: { comparison: Comparison | null }) {
  if (!comparison || comparison.offers.length === 0) return null;
  const { offers, cheapest, currency, reference_price_cents } = comparison;
  // `cheapest` is only set once a match clears the confidence bar — it being
  // null does NOT mean Amazon actually has the best price, just that nothing
  // cleared that bar. A lower price sitting right below unconfirmed language
  // claiming otherwise is exactly the kind of false claim the honesty
  // principle here is supposed to rule out.
  const hasUnconfirmedCheaper =
    !cheapest && offers.some((o) => o.price_cents < reference_price_cents);

  return (
    <section className="compare">
      {cheapest ? (
        <p className="compare-lead">
          Cheaper at <strong>{cheapest.merchant}</strong>:{" "}
          <span className="compare-lead-price">
            {formatMoney(cheapest.price_cents, cheapest.currency || currency)}
          </span>
        </p>
      ) : hasUnconfirmedCheaper ? (
        <p className="compare-lead compare-lead-muted">
          A lower price shows up below, but we couldn&apos;t confidently match
          it to the same model — check it yourself before assuming it&apos;s
          the same item.
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
