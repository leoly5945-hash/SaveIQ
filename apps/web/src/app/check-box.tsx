"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";

import {
  type CheckResult,
  formatMoney,
  looksSubmittable,
  ninetyDayBand,
  requestCheck,
  requestCreateAlert,
  VERDICT_COPY,
} from "@/lib/price-check";

import { Sparkline } from "./sparkline";

type Status = "idle" | "loading" | "ready" | "error";
type AlertState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "done" }
  | { kind: "error"; message: string };

export function CheckBox() {
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");
  const [result, setResult] = useState<CheckResult | null>(null);
  const ranFromUrl = useRef(false);

  async function runCheck(value: string) {
    if (!looksSubmittable(value)) {
      setStatus("error");
      setError("Paste a full amazon.ca product link (or a 10-character ASIN).");
      return;
    }
    setStatus("loading");
    setError("");
    const outcome = await requestCheck(value);
    if (!outcome.ok) {
      setStatus("error");
      setError(outcome.detail);
      setResult(null);
      return;
    }
    setResult(outcome.result);
    setStatus("ready");
  }

  // Bookmarklet / shared link: `/?url=<amazon url>` prefills and auto-runs once.
  // The URL read + setState happen in a microtask so nothing runs on the server
  // and nothing sets state synchronously inside the effect body. A microtask
  // (not setTimeout) so a StrictMode remount's cleanup can't cancel it.
  useEffect(() => {
    if (ranFromUrl.current) return;
    ranFromUrl.current = true;
    queueMicrotask(() => {
      const fromQuery = new URLSearchParams(window.location.search).get("url");
      if (fromQuery && looksSubmittable(fromQuery)) {
        setInput(fromQuery);
        void runCheck(fromQuery);
      }
    });
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runCheck(input.trim());
  }

  return (
    <section className="check">
      <form className="check-form" onSubmit={(e) => void onSubmit(e)}>
        <label className="field check-field">
          <span className="visually-hidden">Amazon.ca product link</span>
          <input
            autoComplete="off"
            inputMode="url"
            maxLength={2048}
            name="url"
            onChange={(e) => setInput(e.target.value)}
            placeholder="Paste an amazon.ca product link…"
            type="text"
            value={input}
          />
        </label>
        <button
          className="check-submit"
          disabled={status === "loading" || input.trim().length === 0}
          type="submit"
        >
          {status === "loading" ? "Checking…" : "Check price"}
        </button>
      </form>

      {status === "idle" ? (
        <p className="state-message">
          We read the price history and tell you: buy now, or wait. No account.
        </p>
      ) : null}
      {status === "error" ? (
        <p className="state-message" role="alert">
          {error}
        </p>
      ) : null}

      {status === "ready" && result ? (
        <VerdictCard result={result} productInput={input.trim()} />
      ) : null}
    </section>
  );
}

function VerdictCard({
  result,
  productInput,
}: {
  result: CheckResult;
  productInput: string;
}) {
  const { assessment } = result;
  const v = VERDICT_COPY[assessment.verdict];
  const currency = assessment.effective_price.currency;
  const effective = assessment.effective_price.effective_cents;
  const band = ninetyDayBand(assessment.intelligence);

  return (
    <article className={`verdict verdict-${v.tone}`}>
      <header className="verdict-head">
        <span className="verdict-badge">{v.label}</span>
        <div className="verdict-headline">
          <p className="verdict-title">{result.title ?? result.provider_product_id}</p>
          <p className="verdict-blurb">{v.blurb}</p>
        </div>
      </header>

      <div className="verdict-price">
        <span className="verdict-now">{formatMoney(effective, currency)}</span>
        <span className="verdict-conf">confidence: {assessment.confidence}</span>
      </div>

      {result.sparkline.length >= 2 ? (
        <div className="verdict-spark">
          <Sparkline points={result.sparkline} tone={v.tone} />
          <div className="verdict-spark-scale">
            <span>{formatMoney(band.min, currency)}</span>
            <span>90 days</span>
            <span>{formatMoney(band.max, currency)}</span>
          </div>
        </div>
      ) : band.min !== null && band.max !== null ? (
        <p className="verdict-band">
          90-day range {formatMoney(band.min, currency)} –{" "}
          {formatMoney(band.max, currency)}
          {band.avg !== null ? (
            <> · avg {formatMoney(band.avg, currency)}</>
          ) : null}
        </p>
      ) : null}

      {assessment.reasons.length > 0 ? (
        <ul className="verdict-reasons">
          {assessment.reasons.map((reason, i) => (
            <li key={i}>{reason}</li>
          ))}
        </ul>
      ) : null}

      {result.product_url ? (
        <a
          className="verdict-cta"
          href={result.product_url}
          rel="sponsored noreferrer"
          target="_blank"
        >
          View it on Amazon.ca
        </a>
      ) : null}

      <AlertForm productInput={productInput} />

      <p className="verdict-fineprint">
        Price is a snapshot from just now — confirm at the retailer before you
        buy. SaveIQ earns an affiliate commission if you buy through the link;
        that never changes the verdict.
      </p>
    </article>
  );
}

function AlertForm({ productInput }: { productInput: string }) {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<AlertState>({ kind: "idle" });

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) {
      setState({ kind: "error", message: "Enter a valid email address." });
      return;
    }
    setState({ kind: "loading" });
    const outcome = await requestCreateAlert({ productInput, email });
    if (!outcome.ok) {
      setState({ kind: "error", message: outcome.detail });
      return;
    }
    setState({ kind: "done" });
  }

  if (state.kind === "done") {
    return (
      <p className="alert-done" role="status">
        Done — we&apos;ll email you once if the price drops. One-time alert; no
        spam.
      </p>
    );
  }

  return (
    <form className="alert-form" onSubmit={(e) => void onSubmit(e)}>
      <label className="field alert-field">
        <span className="visually-hidden">Email for a price-drop alert</span>
        <input
          autoComplete="email"
          name="email"
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email me if it drops"
          type="email"
          value={email}
        />
      </label>
      <button
        className="alert-submit"
        disabled={state.kind === "loading" || email.trim().length === 0}
        type="submit"
      >
        {state.kind === "loading" ? "Setting…" : "Set alert"}
      </button>
      {state.kind === "error" ? (
        <p className="state-message" role="alert">
          {state.message}
        </p>
      ) : null}
    </form>
  );
}
