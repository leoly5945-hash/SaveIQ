"use client";

import { type FormEvent, useMemo, useState } from "react";

const QUICK_SEARCHES = ["buds", "kettle", "pack"];
const SORT_OPTIONS = [
  { label: "Lowest price", value: "price_asc" },
  { label: "Highest price", value: "price_desc" },
  { label: "Merchant A-Z", value: "merchant" },
] as const;
const FRESHNESS_OPTIONS = [
  { label: "All freshness", value: "" },
  { label: "Fresh only", value: "fresh" },
  { label: "Stale only", value: "stale" },
  { label: "Unknown only", value: "unknown" },
] as const;

type SearchResult = {
  offer_id: number;
  product_id: number;
  title: string;
  offer_title: string;
  merchant: string;
  brand: string | null;
  category: string | null;
  price_cents: number;
  sale_price_cents: number | null;
  currency: string;
  market: string;
  availability: string;
  freshness_status: string;
  provider_source: string;
  product_url: string | null;
  has_coupon: boolean;
  has_cashback: boolean;
  match_reasons: string[];
};

type SearchResponse = {
  query: string | null;
  count: number;
  results: SearchResult[];
};

type CouponSummary = {
  code: string;
  description: string;
  discount_type: string;
  discount_value: number;
  expires_at: string | null;
};

type CashbackSummary = {
  rate_type: string;
  rate_value_bps: number;
  expires_at: string | null;
};

type PricePoint = {
  observed_at: string;
  price_cents: number;
  sale_price_cents: number | null;
};

type SourceAttribution = {
  provider_source: string;
  source_record_id: string;
  source_timestamp: string;
  last_successful_update: string | null;
  record_status: string;
};

type OfferDetail = SearchResult & {
  merchant_url: string | null;
  affiliate_url: string | null;
  source_attribution: SourceAttribution;
  coupons: CouponSummary[];
  cashback_offers: CashbackSummary[];
  price_history: PricePoint[];
};

type SearchExperienceProps = {
  searchEndpoint: string;
};

type ClickTargetType = "product" | "affiliate";

function formatMoney(cents: number, currency: string) {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency,
  }).format(cents / 100);
}

function formatPercent(basisPoints: number) {
  return `${(basisPoints / 100).toFixed(2).replace(/\.00$/, "")}%`;
}

export function SearchExperience({ searchEndpoint }: SearchExperienceProps) {
  const [query, setQuery] = useState("wireless earbuds");
  const [merchant, setMerchant] = useState("");
  const [brand, setBrand] = useState("");
  const [category, setCategory] = useState("");
  const [hasCoupon, setHasCoupon] = useState(false);
  const [hasCashback, setHasCashback] = useState(false);
  const [sort, setSort] =
    useState<(typeof SORT_OPTIONS)[number]["value"]>("price_asc");
  const [freshness, setFreshness] =
    useState<(typeof FRESHNESS_OPTIONS)[number]["value"]>("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedOffer, setSelectedOffer] = useState<OfferDetail | null>(null);
  const [detailStatus, setDetailStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [status, setStatus] = useState<
    "idle" | "loading" | "ready" | "empty" | "error"
  >("idle");

  const endpoint = useMemo(() => {
    const params = new URLSearchParams();
    if (query.trim()) {
      params.set("q", query.trim());
    }
    if (merchant.trim()) {
      params.set("merchant", merchant.trim());
    }
    if (brand.trim()) {
      params.set("brand", brand.trim());
    }
    if (category.trim()) {
      params.set("category", category.trim());
    }
    if (hasCoupon) {
      params.set("has_coupon", "true");
    }
    if (hasCashback) {
      params.set("has_cashback", "true");
    }
    params.set("sort", sort);
    if (freshness) {
      params.set("freshness", freshness);
    }
    params.set("limit", "12");
    return `${searchEndpoint}?${params.toString()}`;
  }, [
    brand,
    category,
    hasCashback,
    hasCoupon,
    freshness,
    merchant,
    query,
    searchEndpoint,
    sort,
  ]);

  async function runSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("loading");

    try {
      const response = await fetch(endpoint, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(`Search failed with ${response.status}`);
      }
      const payload = (await response.json()) as SearchResponse;
      setResults(payload.results);
      setSelectedOffer(null);
      setDetailStatus("idle");
      setStatus(payload.count > 0 ? "ready" : "empty");
    } catch {
      setResults([]);
      setSelectedOffer(null);
      setDetailStatus("idle");
      setStatus("error");
    }
  }

  function clearFilters() {
    setQuery("");
    setMerchant("");
    setBrand("");
    setCategory("");
    setHasCoupon(false);
    setHasCashback(false);
    setSort("price_asc");
    setFreshness("");
    setResults([]);
    setSelectedOffer(null);
    setDetailStatus("idle");
    setStatus("idle");
  }

  function applyQuickSearch(term: string) {
    setQuery(term);
    setMerchant("");
    setBrand("");
    setCategory("");
    setHasCoupon(false);
    setHasCashback(false);
    setSort("price_asc");
    setFreshness("");
    setResults([]);
    setSelectedOffer(null);
    setDetailStatus("idle");
    setStatus("idle");
  }

  async function openOfferDetail(offerId: number) {
    setDetailStatus("loading");

    try {
      const response = await fetch(`/api/offers/${offerId}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(`Offer detail failed with ${response.status}`);
      }
      const payload = (await response.json()) as OfferDetail;
      setSelectedOffer(payload);
      setDetailStatus("ready");
    } catch {
      setSelectedOffer(null);
      setDetailStatus("error");
    }
  }

  async function trackClick(offerId: number, targetType: ClickTargetType) {
    try {
      await fetch("/api/clicks", {
        body: JSON.stringify({
          offer_id: offerId,
          referrer: window.location.href,
          target_type: targetType,
        }),
        headers: {
          Accept: "application/json",
          "content-type": "application/json",
        },
        keepalive: true,
        method: "POST",
      });
    } catch {
      // Best-effort mock tracking should never block opening a deal URL.
    }
  }

  return (
    <section className="search-workspace" aria-labelledby="search-heading">
      <div className="search-copy">
        <p className="eyebrow">Mock affiliate search</p>
        <h1 id="search-heading">Find normalized DealHunter offers</h1>
        <p className="search-subtitle">
          Search the seeded mock feed by product, merchant, brand, category,
          coupon, cashback, and freshness.
        </p>
      </div>

      <form className="search-panel" onSubmit={runSearch}>
        <div className="quick-searches" aria-label="Quick searches">
          {QUICK_SEARCHES.map((term) => (
            <button
              key={term}
              type="button"
              onClick={() => applyQuickSearch(term)}
            >
              {term}
            </button>
          ))}
        </div>

        <label className="field search-field">
          <span>Search products</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="wireless earbuds, kettle, pack"
          />
        </label>

        <div className="filter-grid">
          <label className="field">
            <span>Merchant</span>
            <input
              value={merchant}
              onChange={(event) => setMerchant(event.target.value)}
              placeholder="Maple Tech"
            />
          </label>
          <label className="field">
            <span>Brand</span>
            <input
              value={brand}
              onChange={(event) => setBrand(event.target.value)}
              placeholder="Aurora"
            />
          </label>
          <label className="field">
            <span>Category</span>
            <input
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              placeholder="Audio"
            />
          </label>
        </div>

        <div className="filter-row">
          <label className="toggle">
            <input
              type="checkbox"
              checked={hasCoupon}
              onChange={(event) => setHasCoupon(event.target.checked)}
            />
            Coupon available
          </label>
          <label className="toggle">
            <input
              type="checkbox"
              checked={hasCashback}
              onChange={(event) => setHasCashback(event.target.checked)}
            />
            Cashback available
          </label>
          <label className="field compact-field">
            <span>Sort</span>
            <select
              value={sort}
              onChange={(event) => setSort(event.target.value as typeof sort)}
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field compact-field">
            <span>Freshness</span>
            <select
              value={freshness}
              onChange={(event) =>
                setFreshness(event.target.value as typeof freshness)
              }
            >
              {FRESHNESS_OPTIONS.map((option) => (
                <option key={option.label} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={status === "loading"}>
            {status === "loading" ? "Searching" : "Search"}
          </button>
          <button
            className="secondary-button"
            type="button"
            onClick={clearFilters}
          >
            Clear
          </button>
        </div>
      </form>

      <div className="results-panel" aria-live="polite">
        {status === "idle" ? (
          <p className="state-message">
            Run a search or pick a quick search above.
          </p>
        ) : null}
        {status === "empty" ? (
          <div className="state-block">
            <h2>No matching offers found</h2>
            <p className="state-message">
              Clear filters or try a broader term like buds, kettle, or pack.
            </p>
          </div>
        ) : null}
        {status === "error" ? (
          <div className="state-block">
            <h2>Search is unavailable</h2>
            <p className="state-message">
              Check the API health endpoint and try again.
            </p>
          </div>
        ) : null}
        {status === "ready" ? (
          <>
            <div className="results-toolbar">
              <h2>{results.length} matching offers</h2>
              <p>
                Sorted by{" "}
                {SORT_OPTIONS.find((option) => option.value === sort)?.label}
              </p>
            </div>
            <div className="result-list">
              {results.map((result) => {
                const currentPrice =
                  result.sale_price_cents ?? result.price_cents;
                return (
                  <article className="result-card" key={result.offer_id}>
                    <div>
                      <p className="merchant-name">{result.merchant}</p>
                      <h3>{result.title}</h3>
                      <p className="result-meta">
                        {[result.brand, result.category, result.market]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                    </div>
                    <div className="price-block">
                      <p className="price">
                        {formatMoney(currentPrice, result.currency)}
                      </p>
                      {result.sale_price_cents ? (
                        <p className="compare-price">
                          was {formatMoney(result.price_cents, result.currency)}
                        </p>
                      ) : null}
                    </div>
                    <div className="badge-row">
                      <span>{result.freshness_status}</span>
                      {result.has_coupon ? <span>Coupon</span> : null}
                      {result.has_cashback ? <span>Cashback</span> : null}
                      <span>{result.provider_source}</span>
                    </div>
                    <p className="match-reason">
                      Matched on {result.match_reasons.join(", ")}
                    </p>
                    {result.product_url ? (
                      <a
                        className="source-link"
                        href={result.product_url}
                        onClick={() =>
                          void trackClick(result.offer_id, "product")
                        }
                        rel="noreferrer"
                        target="_blank"
                      >
                        Open mock product URL
                      </a>
                    ) : null}
                    <button
                      className="detail-button"
                      type="button"
                      onClick={() => openOfferDetail(result.offer_id)}
                    >
                      View details
                    </button>
                  </article>
                );
              })}
            </div>
            {detailStatus === "loading" ? (
              <p className="state-message detail-state">
                Loading offer detail.
              </p>
            ) : null}
            {detailStatus === "error" ? (
              <p className="state-message detail-state">
                Offer detail is unavailable.
              </p>
            ) : null}
            {selectedOffer ? (
              <OfferDetailPanel offer={selectedOffer} onTrack={trackClick} />
            ) : null}
          </>
        ) : null}
      </div>
    </section>
  );
}

function OfferDetailPanel({
  offer,
  onTrack,
}: {
  offer: OfferDetail;
  onTrack: (offerId: number, targetType: ClickTargetType) => void;
}) {
  const currentPrice = offer.sale_price_cents ?? offer.price_cents;
  const latestPrice = offer.price_history[0];

  return (
    <aside className="offer-detail" aria-label="Offer detail">
      <div className="detail-heading">
        <div>
          <p className="eyebrow">Offer detail</p>
          <h2>{offer.title}</h2>
          <p className="result-meta">
            {offer.merchant} · {offer.provider_source} · {offer.market}
          </p>
        </div>
        <div className="price-block">
          <p className="price">{formatMoney(currentPrice, offer.currency)}</p>
          {offer.sale_price_cents ? (
            <p className="compare-price">
              was {formatMoney(offer.price_cents, offer.currency)}
            </p>
          ) : null}
        </div>
      </div>

      <p className="mock-warning">
        Mock staging data only. This is not a real merchant checkout or live
        affiliate integration.
      </p>

      <div className="detail-grid">
        <section>
          <h3>Commercial context</h3>
          <dl>
            <div>
              <dt>Availability</dt>
              <dd>{offer.availability}</dd>
            </div>
            <div>
              <dt>Freshness</dt>
              <dd>{offer.freshness_status}</dd>
            </div>
            <div>
              <dt>Latest observed price</dt>
              <dd>
                {latestPrice
                  ? formatMoney(
                      latestPrice.sale_price_cents ?? latestPrice.price_cents,
                      offer.currency
                    )
                  : "Not available"}
              </dd>
            </div>
          </dl>
        </section>

        <section>
          <h3>Coupons</h3>
          {offer.coupons.length > 0 ? (
            <ul>
              {offer.coupons.map((coupon) => (
                <li key={coupon.code}>
                  <strong>{coupon.code}</strong>
                  <span>{coupon.description}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="state-message">No active coupon for this merchant.</p>
          )}
        </section>

        <section>
          <h3>Cashback</h3>
          {offer.cashback_offers.length > 0 ? (
            <ul>
              {offer.cashback_offers.map((cashback) => (
                <li key={`${cashback.rate_type}-${cashback.rate_value_bps}`}>
                  <strong>{formatPercent(cashback.rate_value_bps)}</strong>
                  <span>{cashback.rate_type}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="state-message">
              No active cashback for this merchant.
            </p>
          )}
        </section>

        <section>
          <h3>Source attribution</h3>
          <dl>
            <div>
              <dt>Provider</dt>
              <dd>{offer.source_attribution.provider_source}</dd>
            </div>
            <div>
              <dt>Record</dt>
              <dd>{offer.source_attribution.source_record_id}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{offer.source_attribution.record_status}</dd>
            </div>
          </dl>
        </section>
      </div>

      <div className="detail-actions">
        {offer.product_url ? (
          <a
            href={offer.product_url}
            onClick={() => onTrack(offer.offer_id, "product")}
            rel="noreferrer"
            target="_blank"
          >
            Open mock product URL
          </a>
        ) : null}
        {offer.affiliate_url ? (
          <a
            href={offer.affiliate_url}
            onClick={() => onTrack(offer.offer_id, "affiliate")}
            rel="noreferrer"
            target="_blank"
          >
            Open mock affiliate URL
          </a>
        ) : null}
      </div>
    </aside>
  );
}
