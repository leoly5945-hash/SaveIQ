import { formatMoney, type MerchantOffer } from "@/lib/price-check";

/**
 * The verdict is anchored to Amazon on purpose — it's the only CA retailer
 * with an affordable 90-day price-history feed, which is what "buy now or
 * wait" is computed from. But the BUY button isn't Amazon's to keep: when the
 * comparison block has already cleared a cheaper offer as a reliable match
 * (`comparison.cheapest` is only set at match_confidence >= 0.65, and every
 * offer there is at or below the Amazon price), that's the honest "buy"
 * action — Amazon becomes the fallback. Rendered twice per card — once near
 * the top (`top`, with a gentle motion-safe pulse) and once at the bottom.
 */
export function BuyCta({
  amazonHref,
  amazonPriceCents,
  currency,
  cheapest,
  top = false,
}: {
  amazonHref: string;
  amazonPriceCents: number;
  currency: string;
  cheapest: MerchantOffer | null;
  top?: boolean;
}) {
  const ctaClass = top ? "verdict-cta verdict-cta-top" : "verdict-cta";

  if (cheapest?.url) {
    return (
      <div className="buy-cta-group">
        <a
          className={ctaClass}
          href={cheapest.url}
          rel="sponsored nofollow noopener noreferrer"
          target="_blank"
        >
          Buy at {cheapest.merchant} —{" "}
          {formatMoney(cheapest.price_cents, cheapest.currency || currency)}
          <span aria-hidden="true"> →</span>
        </a>
        <a
          className="buy-cta-secondary"
          href={amazonHref}
          rel="sponsored nofollow noopener noreferrer"
          target="_blank"
        >
          or on Amazon.ca — {formatMoney(amazonPriceCents, currency)}
        </a>
      </div>
    );
  }

  return (
    <a
      className={ctaClass}
      href={amazonHref}
      rel="sponsored nofollow noopener noreferrer"
      target="_blank"
    >
      Buy on Amazon.ca
      <span aria-hidden="true"> →</span>
    </a>
  );
}
