import Link from "next/link";

import { CategoryIcon } from "@/components/category-icon";

import {
  dealPath,
  describeVsAverage,
  formatMoney,
  formatObservedDate,
  type FeaturedDeal,
} from "@/lib/featured-deals";

function PriceDropCard({ deal }: { deal: FeaturedDeal }) {
  const latest = deal.latest_price;
  if (!latest) {
    return null;
  }
  const versus = describeVsAverage(latest);
  const recorded = formatObservedDate(latest.observed_at);
  return (
    <li className="deal-card price-drop-card">
      <div className="deal-card-top">
        <CategoryIcon slug={deal.category_slug} />
        <p className="deal-card-merchant">{deal.merchant}</p>
      </div>
      <h3 className="deal-card-title">
        <Link href={dealPath(deal)}>{deal.title}</Link>
      </h3>
      <p className="deal-card-price">
        {formatMoney(latest.price_cents, latest.currency)}
      </p>
      {versus ? <p className="price-drop-versus">{versus}</p> : null}
      {recorded ? (
        <p className="deal-card-checked">
          Recorded {recorded} — confirm at {deal.merchant}
        </p>
      ) : null}
      <p className="deal-card-links">
        <Link className="deal-card-cta" href={dealPath(deal)}>
          See details
        </Link>
      </p>
    </li>
  );
}

export function PriceDropGrid({ deals }: { deals: FeaturedDeal[] }) {
  return (
    <ul className="deal-grid">
      {deals.map((deal) => (
        <PriceDropCard deal={deal} key={deal.offer_id} />
      ))}
    </ul>
  );
}
