"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";

import {
  type DiscoverHit,
  type DiscoverResult,
  requestDiscover,
} from "@/lib/discover";
import { formatMoney } from "@/lib/price-check";

type Status = "idle" | "loading" | "ready" | "error";

export function DiscoverBox() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");
  const [result, setResult] = useState<DiscoverResult | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = q.trim();
    if (value.length < 2) return;
    setStatus("loading");
    setError("");
    const outcome = await requestDiscover(value);
    if (!outcome.ok) {
      setStatus("error");
      setError(outcome.detail);
      setResult(null);
      return;
    }
    setResult(outcome.result);
    setStatus("ready");
  }

  return (
    <section className="discover">
      <form className="discover-form" onSubmit={(e) => void onSubmit(e)}>
        <label className="field discover-field">
          <span className="visually-hidden">Describe what you want to buy</span>
          <input
            autoComplete="off"
            maxLength={240}
            name="q"
            onChange={(e) => setQ(e.target.value)}
            placeholder="Describe it — “power bank under $100”, “robot vacuum”"
            type="text"
            value={q}
          />
        </label>
        <button
          className="discover-submit"
          disabled={status === "loading" || q.trim().length < 2}
          type="submit"
        >
          {status === "loading" ? "Searching…" : "Search"}
        </button>
      </form>

      {status === "error" ? (
        <p className="state-message" role="alert">
          {error}
        </p>
      ) : null}

      {status === "ready" && result ? <Results result={result} /> : null}
    </section>
  );
}

function Results({ result }: { result: DiscoverResult }) {
  const { query, hits, price_probed } = result;
  if (hits.length === 0) {
    return (
      <p className="state-message">
        Nothing found for “{query.search_terms}”. Try different words.
      </p>
    );
  }
  return (
    <div className="discover-results">
      <p className="discover-summary">
        {query.search_terms}
        {query.price_max_cents
          ? ` · under ${formatMoney(query.price_max_cents, "CAD")}`
          : ""}
        {query.price_min_cents
          ? ` · over ${formatMoney(query.price_min_cents, "CAD")}`
          : ""}
      </p>
      <ul className="discover-list">
        {hits.map((h) => (
          <HitRow key={h.product_id} hit={h} probed={price_probed} />
        ))}
      </ul>
      <p className="discover-note">
        From an Amazon.ca search. Open one for the full buy / wait verdict and the
        ways to get it.
      </p>
    </div>
  );
}

function HitRow({ hit, probed }: { hit: DiscoverHit; probed: boolean }) {
  return (
    <li className={hit.in_budget === false ? "discover-hit discover-over" : "discover-hit"}>
      <span className="discover-title">{hit.title}</span>
      <span className="discover-price">
        {hit.price_cents != null
          ? formatMoney(hit.price_cents, hit.currency)
          : probed
            ? "—"
            : ""}
        {hit.in_budget === false ? " · over budget" : ""}
      </span>
      <Link className="discover-link" href={`/check/${hit.product_id}`}>
        Check
      </Link>
    </li>
  );
}
