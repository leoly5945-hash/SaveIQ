import Link from "next/link";

import {
  categoryPath,
  dealPath,
  formatMoney,
  formatPriceCheckedDate,
  type FeaturedDeal,
} from "@/lib/featured-deals";

export function DealCard({ deal }: { deal: FeaturedDeal }) {
  const checked = formatPriceCheckedDate(deal.price_checked);
  return (
    <li className="deal-card">
      <p className="deal-card-merchant">{deal.merchant}</p>
      <h3 className="deal-card-title">
        <Link href={dealPath(deal)}>{deal.title}</Link>
      </h3>
      {deal.blurb ? <p className="deal-card-blurb">{deal.blurb}</p> : null}
      <p className="deal-card-price">
        {formatMoney(deal.price_cents, deal.currency)}
      </p>
      {checked ? (
        <p className="deal-card-checked">Price checked {checked}</p>
      ) : null}
      <p className="deal-card-links">
        <Link className="deal-card-cta" href={dealPath(deal)}>
          See details
        </Link>
        {deal.category && deal.category_slug ? (
          <Link
            className="deal-card-cat"
            href={categoryPath(deal.category_slug)}
          >
            {deal.category}
          </Link>
        ) : null}
      </p>
    </li>
  );
}

export function DealGrid({ deals }: { deals: FeaturedDeal[] }) {
  return (
    <ul className="deal-grid">
      {deals.map((deal) => (
        <DealCard deal={deal} key={deal.offer_id} />
      ))}
    </ul>
  );
}
