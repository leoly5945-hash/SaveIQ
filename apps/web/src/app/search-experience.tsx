"use client";

import { type FormEvent, useMemo, useState } from "react";

const QUICK_SEARCHES = ["buds", "coffee", "backpack"];

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

  function clearFilters() {
    setQuery("");
    setMerchant("");
    setBrand("");
    setCategory("");
    setHasCoupon(false);
    setHasCashback(false);
    setResults([]);
    setStatus("idle");
  }

  function applyQuickSearch(term: string) {
    setQuery(term);
    setMerchant("");
    setBrand("");
    setCategory("");
    setHasCoupon(false);
    setHasCashback(false);
    setResults([]);
    setStatus("idle");
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
              Clear filters or try a broader term like buds, coffee, or
              backpack.
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
              <p>Sorted by lowest current price</p>
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
                    {result.product_url ? (
                      <a
                        className="source-link"
                        href={result.product_url}
                        rel="noreferrer"
                        target="_blank"
                      >
                        Open mock product URL
                      </a>
                    ) : null}
                  </article>
                );
              })}
            </div>
          </>
        ) : null}
      </div>
    </section>
  );
}
