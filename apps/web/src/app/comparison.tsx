import { type Comparison, formatMoney } from "@/lib/price-check";

/**
 * Cross-merchant offers for the same product (from Google Shopping data).
 * Renders nothing when there are no matched offers.
 */
export function ComparisonBlock({ comparison }: { comparison: Comparison | null }) {
  if (!comparison) return null;
  const { offers, cheapest, currency, reference_price_cents } = comparison;
  const ebay = comparison.also_on_ebay ?? null;
  if (offers.length === 0 && !ebay) return null;
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

      {offers.length > 0 ? (
        <ul className="compare-list">
          {offers.map((o) => (
            <li key={o.merchant}>
              <span className="compare-merchant">
                {o.merchant}
                {o.detail ? <span className="compare-detail">{o.detail}</span> : null}
              </span>
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
      ) : null}
      {ebay ? (
        <p className="compare-ebay">
          Also new on eBay.ca:{" "}
          <strong>{formatMoney(ebay.price_cents, ebay.currency || currency)}</strong>{" "}
          including shipping
          {ebay.price_cents > reference_price_cents ? " — not cheaper than Amazon.ca" : ""}.
          {ebay.detail ? <span className="compare-detail">{ebay.detail}</span> : null}
          {ebay.url ? (
            <a
              className="compare-link"
              href={ebay.url}
              rel="sponsored noreferrer"
              target="_blank"
            >
              View on eBay
            </a>
          ) : null}
        </p>
      ) : null}
      <p className="compare-note">
        Store prices from Google Shopping, matched by product name — confirm the
        model before you buy. eBay: new listings only, from Canadian sellers with
        strong feedback, shipping included.
      </p>
    </section>
  );
}
