import { type AmazonSpread, formatMoney } from "@/lib/price-check";

const CONDITION_LABEL: Record<string, string> = {
  new: "other new sellers",
  used: "used / renewed",
};

/**
 * The spread of Amazon sellers around the buy box — other new listings and
 * used/renewed stock. Renders nothing when the buy box is the only thing worth
 * showing.
 */
export function OfferSpread({ spread }: { spread: AmazonSpread | null }) {
  if (!spread || spread.tiers.length === 0) return null;
  const { currency, savings_vs_buy_box_cents, lowest_overall_cents, tiers } =
    spread;

  return (
    <section className="spread">
      {savings_vs_buy_box_cents > 0 ? (
        <p className="spread-lead">
          On Amazon itself, from{" "}
          <span className="spread-lead-price">
            {formatMoney(lowest_overall_cents, currency)}
          </span>{" "}
          — {formatMoney(savings_vs_buy_box_cents, currency)} under the buy box.
        </p>
      ) : (
        <p className="spread-lead spread-lead-muted">
          The buy box is the cheapest Amazon offer right now.
        </p>
      )}

      <ul className="spread-list">
        {tiers.map((t) => (
          <li key={t.condition}>
            <span className="spread-cond">
              {t.offer_count} {CONDITION_LABEL[t.condition] ?? t.condition}
            </span>
            <span className="spread-price">
              from {formatMoney(t.lowest_total_cents, currency)}
              {t.fba_available ? " · ships from Amazon" : ""}
            </span>
          </li>
        ))}
      </ul>
      <p className="spread-note">
        Live Amazon offers (price + shipping). Used / renewed condition varies by
        seller — check the listing.
      </p>
    </section>
  );
}
