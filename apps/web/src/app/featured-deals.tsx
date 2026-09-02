"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  AMAZON_ASSOCIATE_DISCLOSURE,
  dealPath,
  FEATURED_DEALS_BLURB,
  FEATURED_DEALS_HEADING,
  formatMoney,
  formatPriceCheckedDate,
  requestFeaturedDeals,
  type FeaturedDeal,
} from "@/lib/featured-deals";

export function FeaturedDeals() {
  const [deals, setDeals] = useState<FeaturedDeal[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let active = true;
    void requestFeaturedDeals().then((result) => {
      if (!active) {
        return;
      }
      setDeals(result);
      setLoaded(true);
    });
    return () => {
      active = false;
    };
  }, []);

  if (!loaded || deals.length === 0) {
    return null;
  }

  return (
    <section className="home-featured" aria-labelledby="featured-deals-heading">
      <div className="home-featured-head">
        <h2 id="featured-deals-heading">{FEATURED_DEALS_HEADING}</h2>
        <p>{FEATURED_DEALS_BLURB}</p>
      </div>

      <ul className="home-featured-list">
        {deals.map((deal) => {
          const checked = formatPriceCheckedDate(deal.price_checked);
          return (
            <li className="home-featured-card" key={deal.offer_id}>
              <p className="merchant-name">{deal.merchant}</p>
              <h3>
                <Link href={dealPath(deal)}>{deal.title}</Link>
              </h3>
              {deal.blurb ? (
                <p className="home-featured-blurb">{deal.blurb}</p>
              ) : null}
              <p className="price">{formatMoney(deal.price_cents, deal.currency)}</p>
              {checked ? (
                <p className="home-featured-checked">
                  Price checked {checked} — confirm at {deal.merchant}
                </p>
              ) : null}
              <Link className="source-link" href={dealPath(deal)}>
                See details
              </Link>
            </li>
          );
        })}
      </ul>

      <p className="home-featured-more">
        <Link href="/deals">Browse all deals →</Link>
      </p>
      <p className="home-featured-disclosure">{AMAZON_ASSOCIATE_DISCLOSURE}</p>
    </section>
  );
}
