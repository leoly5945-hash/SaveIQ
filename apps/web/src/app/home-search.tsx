"use client";

import { type FormEvent, useState } from "react";

import { getOrCreateAnonymousUserId } from "@/lib/anonymous-user";
import {
  dealLink,
  formatMoney,
  HOME_INTENT_PLACEHOLDER,
  requestHomeRecommendations,
  trackHomeDealClick,
  type HomeOffer,
} from "@/lib/home-recommendations";

type SearchStatus = "idle" | "loading" | "ready" | "empty" | "error";

export function HomeSearch() {
  const [intent, setIntent] = useState("");
  const [status, setStatus] = useState<SearchStatus>("idle");
  const [offers, setOffers] = useState<HomeOffer[]>([]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = intent.trim();
    if (query.length < 3) {
      return;
    }
    const anonymousUserId = getOrCreateAnonymousUserId();
    setStatus("loading");
    const result = await requestHomeRecommendations({
      intent: query,
      anonymousUserId,
    });
    if (!result.ok) {
      setOffers([]);
      setStatus("error");
      return;
    }
    setOffers(result.offers);
    setStatus(result.offers.length > 0 ? "ready" : "empty");
  }

  const canSubmit = intent.trim().length >= 3 && status !== "loading";

  return (
    <section className="home-search">
      <form className="home-search-form" onSubmit={(event) => void onSubmit(event)}>
        <label className="field home-intent-field">
          <span className="visually-hidden">{HOME_INTENT_PLACEHOLDER}</span>
          <input
            autoComplete="off"
            maxLength={240}
            minLength={3}
            name="intent"
            onChange={(event) => setIntent(event.target.value)}
            placeholder={HOME_INTENT_PLACEHOLDER}
            type="search"
            value={intent}
          />
        </label>
        <button className="home-submit" disabled={!canSubmit} type="submit">
          {status === "loading" ? "Searching…" : "Find deals"}
        </button>
      </form>

      {status === "idle" ? (
        <p className="state-message">Type what you want and search. No account needed.</p>
      ) : null}
      {status === "loading" ? (
        <p className="state-message" role="status">
          Searching for deals…
        </p>
      ) : null}
      {status === "empty" ? (
        <p className="state-message" role="status">
          No deals found. Try a broader search.
        </p>
      ) : null}
      {status === "error" ? (
        <p className="state-message" role="alert">
          Couldn&apos;t load deals. Please try again.
        </p>
      ) : null}

      {status === "ready" ? (
        <ul className="home-result-list">
          {offers.map((offer) => {
            const link = dealLink(offer);
            const price = offer.sale_price_cents ?? offer.price_cents;
            const percentOff =
              offer.sale_price_cents && offer.price_cents > 0
                ? Math.round(
                    (1 - offer.sale_price_cents / offer.price_cents) * 100
                  )
                : 0;
            return (
              <li className="home-result-card" key={offer.offer_id}>
                {percentOff > 0 ? (
                  <span className="home-discount">−{percentOff}%</span>
                ) : null}
                <p className="merchant-name">{offer.merchant}</p>
                <h2>{offer.offer_title || offer.title}</h2>
                <div className="home-price-row">
                  <p className="price">{formatMoney(price, offer.currency)}</p>
                  {offer.sale_price_cents ? (
                    <p className="compare-price">
                      was {formatMoney(offer.price_cents, offer.currency)}
                    </p>
                  ) : null}
                </div>
                <div className="badge-row">
                  {offer.has_coupon ? <span>Coupon</span> : null}
                  {offer.has_cashback ? <span>Cashback</span> : null}
                </div>
                {link ? (
                  <a
                    className="source-link"
                    href={link.href}
                    onClick={() =>
                      trackHomeDealClick({
                        offerId: offer.offer_id,
                        targetType: link.targetType,
                        anonymousUserId: getOrCreateAnonymousUserId(),
                      })
                    }
                    rel="noreferrer"
                    target="_blank"
                  >
                    View deal
                  </a>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
