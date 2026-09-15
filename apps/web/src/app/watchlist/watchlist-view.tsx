"use client";

import { type FormEvent, useState } from "react";

import { getApiBaseUrl } from "@/lib/config";
import {
  formatMoney,
  requestWatchlist,
  VERDICT_COPY,
  type WatchlistItem,
} from "@/lib/price-check";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "done"; items: WatchlistItem[] };

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function WatchlistView() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  async function load(value: string) {
    if (!EMAIL_RE.test(value.trim())) {
      setState({ kind: "error", message: "Enter a valid email address." });
      return;
    }
    setState({ kind: "loading" });
    const outcome = await requestWatchlist(value);
    if (!outcome.ok) {
      setState({ kind: "error", message: outcome.detail });
      return;
    }
    setState({ kind: "done", items: outcome.items });
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void load(email);
  }

  function onRemoved(alertId: number) {
    if (state.kind !== "done") return;
    setState({ kind: "done", items: state.items.filter((i) => i.alert_id !== alertId) });
  }

  return (
    <div className="watchlist-view">
      <form className="watchlist-form" onSubmit={onSubmit}>
        <label className="field">
          <span className="visually-hidden">Your email</span>
          <input
            autoComplete="email"
            name="email"
            onChange={(e) => setEmail(e.target.value)}
            placeholder="The email you used for alerts"
            type="email"
            value={email}
          />
        </label>
        <button
          className="watchlist-submit"
          disabled={state.kind === "loading" || email.trim().length === 0}
          type="submit"
        >
          {state.kind === "loading" ? "Loading…" : "Show my watchlist"}
        </button>
      </form>

      {state.kind === "error" ? (
        <p className="state-message" role="alert">
          {state.message}
        </p>
      ) : null}

      {state.kind === "done" ? (
        state.items.length === 0 ? (
          <p className="watchlist-empty">
            Nothing tracked under that email yet — set an alert from any price
            check to add one.
          </p>
        ) : (
          <ul className="showcase-grid watchlist-grid">
            {state.items.map((item) => (
              <WatchlistCard item={item} key={item.alert_id} onRemoved={onRemoved} />
            ))}
          </ul>
        )
      ) : null}
    </div>
  );
}

function WatchlistCard({
  item,
  onRemoved,
}: {
  item: WatchlistItem;
  onRemoved: (alertId: number) => void;
}) {
  const [removing, setRemoving] = useState(false);
  const v = item.verdict ? VERDICT_COPY[item.verdict] : null;
  const title = item.title ?? item.provider_product_id;

  async function onRemove() {
    setRemoving(true);
    try {
      // `unsubscribe_url` is a saveiq.ca *page* link meant for the email
      // (see AlertsUnsubscribePage) — here we already have JS, so call the
      // API directly instead of round-tripping through that page. The API's
      // CORS allowlist already includes this site's own origin.
      const token = new URL(item.unsubscribe_url).searchParams.get("token");
      if (token) {
        const url = new URL("/alerts/unsubscribe", getApiBaseUrl());
        url.searchParams.set("token", token);
        await fetch(url, { headers: { Accept: "application/json" } });
      }
    } finally {
      onRemoved(item.alert_id);
    }
  }

  return (
    <li className={`showcase-card watchlist-card showcase-card-${v?.tone ?? "unknown"}`}>
      <a
        className="watchlist-card-link"
        href={`/check/${item.provider_product_id}`}
      >
        {v ? <span className="showcase-badge">{v.label}</span> : null}
        <p className="showcase-title">{title}</p>
        {item.price_cents !== null ? (
          <p className="showcase-amazon">
            Amazon.ca <strong>{formatMoney(item.price_cents, item.currency)}</strong>
          </p>
        ) : (
          <p className="showcase-amazon">Price not checked yet</p>
        )}
        <span className="showcase-cta" aria-hidden="true">
          See full comparison →
        </span>
      </a>
      <button
        className="watchlist-remove"
        disabled={removing}
        onClick={() => void onRemove()}
        type="button"
      >
        {removing ? "Removing…" : "Remove"}
      </button>
    </li>
  );
}
