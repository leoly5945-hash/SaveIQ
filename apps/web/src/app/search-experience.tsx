"use client";

import { type FormEvent, useMemo, useState } from "react";

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
};

type SearchResponse = {
  query: string | null;
  count: number;
  results: SearchResult[];
};

type SearchExperienceProps = {
  searchEndpoint: string;
};

function formatMoney(cents: number, currency: string) {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency,
  }).format(cents / 100);
}

export function SearchExperience({ searchEndpoint }: SearchExperienceProps) {
  const [query, setQuery] = useState("wireless earbuds");
  const [merchant, setMerchant] = useState("");
  const [brand, setBrand] = useState("");
  const [category, setCategory] = useState("");
  const [hasCoupon, setHasCoupon] = useState(false);
  const [hasCashback, setHasCashback] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);
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
    params.set("freshness", "fresh");
    params.set("limit", "12");
    return `${searchEndpoint}?${params.toString()}`;
  }, [
    brand,
    category,
    hasCashback,
    hasCoupon,
    merchant,
    query,
    searchEndpoint,
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
      setStatus(payload.count > 0 ? "ready" : "empty");
    } catch {
      setResults([]);
      setStatus("error");
    }
  }

  return (
    <section className="search-workspace" aria-labelledby="search-heading">
      <div className="search-copy">
        <p className="eyebrow">Mock affiliate search</p>
        <h1 id="search-heading">Find normalized DealHunter offers</h1>
      </div>

      <form className="search-panel" onSubmit={runSearch}>
        <label className="field search-field">
          <span>Search products</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="wireless earbuds, coffee, backpack"
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
          <button type="submit" disabled={status === "loading"}>
            {status === "loading" ? "Searching" : "Search"}
          </button>
        </div>
      </form>

      <div className="results-panel" aria-live="polite">
        {status === "idle" ? (
          <p className="state-message">
            Run a search against the staging API mock feed.
          </p>
        ) : null}
        {status === "empty" ? (
          <p className="state-message">No matching offers found.</p>
        ) : null}
        {status === "error" ? (
          <p className="state-message">
            Search is unavailable. Check the API health endpoint.
          </p>
        ) : null}
        {status === "ready" ? (
          <div className="result-list">
            {results.map((result) => {
              const currentPrice =
                result.sale_price_cents ?? result.price_cents;
              return (
                <article className="result-card" key={result.offer_id}>
                  <div>
                    <p className="merchant-name">{result.merchant}</p>
                    <h2>{result.title}</h2>
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
                </article>
              );
            })}
          </div>
        ) : null}
      </div>
    </section>
  );
}
