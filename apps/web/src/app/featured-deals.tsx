"use client";

import { useEffect, useState } from "react";

import { getOrCreateAnonymousUserId } from "@/lib/anonymous-user";
import {
  AMAZON_ASSOCIATE_DISCLOSURE,
  FEATURED_DEALS_BLURB,
  FEATURED_DEALS_HEADING,
  featuredDealHref,
  formatPriceCheckedDate,
  requestFeaturedDeals,
  type FeaturedDeal,
} from "@/lib/featured-deals";
import { formatMoney, withAnonymousId } from "@/lib/home-recommendations";

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
              <h3>{deal.title}</h3>
              {deal.blurb ? (
                <p className="home-featured-blurb">{deal.blurb}</p>
              ) : null}
              <p className="price">{formatMoney(deal.price_cents, deal.currency)}</p>
              {checked ? (
                <p className="home-featured-checked">
                  Price checked {checked} — confirm at {deal.merchant}
                </p>
              ) : null}
              <a
                className="source-link"
                href={withAnonymousId(
                  featuredDealHref(deal),
                  getOrCreateAnonymousUserId()
                )}
                rel="sponsored noreferrer"
                target="_blank"
              >
                View deal
              </a>
            </li>
          );
        })}
      </ul>

      <p className="home-featured-disclosure">{AMAZON_ASSOCIATE_DISCLOSURE}</p>
    </section>
  );
}
