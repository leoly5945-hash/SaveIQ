import Link from "next/link";

import {
  fetchCheckByAsin,
  formatMoney,
  VERDICT_COPY,
  type CheckResult,
} from "@/lib/price-check";
import { SHOWCASE_ASINS } from "@/lib/showcase-products";

/**
 * "Compare across stores" — a fixed set of products chosen because a real
 * cross-merchant comparison comes back for them (Best Buy, Dyson Canada,
 * Dell Canada, …). No affiliate requirement: this is about showing the
 * comparison actually works and giving people something to click, not
 * revenue — offers render whether or not they're tagged.
 */
export async function MultiStoreShowcase() {
  const results = await Promise.all(SHOWCASE_ASINS.map((asin) => fetchCheckByAsin(asin)));
  const cards = results.filter(
    (r): r is CheckResult => r !== null && (r.comparison?.offers.length ?? 0) > 0
  );
  if (cards.length === 0) return null;

  return (
    <section className="showcase">
      <div className="showcase-head">
        <h2>Compare across stores</h2>
        <p>
          The same product, checked at other Canadian retailers — not just
          Amazon.
        </p>
      </div>
      <div className="showcase-grid">
        {cards.map((r) => (
          <ShowcaseCard key={r.provider_product_id} result={r} />
        ))}
      </div>
    </section>
  );
}

function ShowcaseCard({ result }: { result: CheckResult }) {
  const { assessment, comparison } = result;
  const v = VERDICT_COPY[assessment.verdict];
  const currency = assessment.effective_price.currency;
  const effective = assessment.effective_price.effective_cents;
  // Offers come back cheapest-first, which can push a recognizable name
  // (a brand's own store is rarely the cheapest reseller) out of a top-3
  // window. 5 keeps the card readable while giving that more room.
  const offers = (comparison?.offers ?? []).slice(0, 5);

  return (
    <Link
      className={`showcase-card showcase-card-${v.tone}`}
      href={`/check/${result.provider_product_id}`}
    >
      <span className="showcase-badge">{v.label}</span>
      <p className="showcase-title">{result.title ?? result.provider_product_id}</p>
      <p className="showcase-amazon">
        Amazon.ca <strong>{formatMoney(effective, currency)}</strong>
      </p>
      <ul className="showcase-offers">
        {offers.map((o) => (
          <li key={o.merchant}>
            <span>{o.merchant}</span>
            <span>{formatMoney(o.price_cents, o.currency || currency)}</span>
          </li>
        ))}
      </ul>
      <span className="showcase-cta" aria-hidden="true">
        See full comparison →
      </span>
    </Link>
  );
}
