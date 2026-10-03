"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { type AcquireResult, requestAcquire } from "@/lib/acquire";
import {
  type AlternativesResult,
  requestAlternatives,
} from "@/lib/alternatives";
import {
  amazonButtonHref,
  type CheckResult,
  CHECK_REQUEST_EVENT,
  formatMoney,
  looksLikeBarcode,
  looksSubmittable,
  ninetyDayBand,
  requestBarcode,
  requestCheck,
  requestCreateAlert,
  VERDICT_COPY,
} from "@/lib/price-check";

import { BarcodeScanButton } from "@/components/barcode-scan";
import { DiscountChecks, PricePositionBar } from "@/components/price-position";
import { ProductImage } from "@/components/product-image";

import { AcquireBlock } from "./acquire-block";
import { AlternativesBlock } from "./alternatives-block";
import { BuyCta } from "./buy-cta";
import { ComparisonBlock } from "./comparison";
import { OfferSpread } from "./offer-spread";
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
  const [acquire, setAcquire] = useState<AcquireResult | null>(null);
  const [alternatives, setAlternatives] = useState<AlternativesResult | null>(
    null
  );
  const ranFromUrl = useRef(false);
  const sectionRef = useRef<HTMLElement>(null);

  async function runCheck(raw: string) {
    let value = raw;
    // A barcode (typed, or from the camera) is first turned into its ASIN.
    if (looksLikeBarcode(value)) {
      setStatus("loading");
      setError("");
      const found = await requestBarcode(value);
      if (!found.ok) {
        setStatus("error");
        setError(found.detail);
        setResult(null);
        return;
      }
      value = found.asin;
      setInput(value);
    }
    if (!looksSubmittable(value)) {
      setStatus("error");
      setError(
        "Paste a full amazon.ca product link, a 10-character ASIN or a barcode number."
      );
      return;
    }
    setStatus("loading");
    setError("");
    setAcquire(null);
    setAlternatives(null);
    const outcome = await requestCheck(value);
    if (!outcome.ok) {
      setStatus("error");
      setError(outcome.detail);
      setResult(null);
      return;
    }
    setResult(outcome.result);
    setStatus("ready");
    // Layer 2 is a follow-on — the verdict shows without waiting for it.
    void requestAcquire(value).then(setAcquire);
    // "buy this instead" only when it's a poor time to buy this one.
    const v = outcome.result.assessment.verdict;
    if (v === "WAIT" || v === "UNKNOWN") {
      void requestAlternatives(value).then(setAlternatives);
    }
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

  // A barcode scanned from the main search box runs here, where the verdict
  // is shown; bring this box into view so the result isn't off-screen.
  useEffect(() => {
    function onRequest(event: Event) {
      const value = (event as CustomEvent<string>).detail;
      if (typeof value !== "string" || !value.trim()) return;
      setInput(value);
      sectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      void runCheck(value);
    }
    window.addEventListener(CHECK_REQUEST_EVENT, onRequest);
    return () => window.removeEventListener(CHECK_REQUEST_EVENT, onRequest);
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runCheck(input.trim());
  }

  return (
    <section className="check" ref={sectionRef}>
      <form className="check-form pill-search" onSubmit={(e) => void onSubmit(e)}>
        <label className="pill-search-field">
          <svg
            aria-hidden="true"
            className="pill-search-icon"
            fill="none"
            height="22"
            stroke="currentColor"
            strokeLinecap="round"
            strokeWidth="2.2"
            viewBox="0 0 24 24"
            width="22"
          >
            <path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1" />
            <path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1" />
          </svg>
          <span className="visually-hidden">Amazon.ca product link</span>
          <input
            autoComplete="off"
            inputMode="url"
            maxLength={2048}
            name="url"
            onChange={(e) => setInput(e.target.value)}
            placeholder="Paste an amazon.ca link or a barcode number…"
            type="text"
            value={input}
          />
        </label>
        <BarcodeScanButton
          onCode={(code) => {
            setInput(code);
            void runCheck(code);
          }}
        />
        <button
          className="pill-search-chip"
          disabled={status === "loading" || input.trim().length === 0}
          type="submit"
        >
          {status === "loading" ? "Checking…" : "Check price"}
        </button>
      </form>

      {status === "idle" ? (
        <p className="check-price-hint">
          We read the price history and tell you: buy now, or wait. Leave
          your email and we&apos;ll tell you when it drops.
        </p>
      ) : null}
      {status === "error" ? (
        <p className="state-message" role="alert">
          {error}
        </p>
      ) : null}

      {/* Visible immediately next to the paste box — not something you only
          reach after a check finishes. */}
      <AlertForm productInput={input.trim()} />

      {status === "ready" && result ? (
        <VerdictCard result={result} acquire={acquire} alternatives={alternatives} />
      ) : null}
    </section>
  );
}

function VerdictCard({
  result,
  acquire,
  alternatives,
}: {
  result: CheckResult;
  acquire: AcquireResult | null;
  alternatives: AlternativesResult | null;
}) {
  const { assessment } = result;
  const v = VERDICT_COPY[assessment.verdict];
  const currency = assessment.effective_price.currency;
  const effective = assessment.effective_price.effective_cents;
  const band = ninetyDayBand(assessment.intelligence);
  const name = result.title ?? result.provider_product_id;

  return (
    <article className={`verdict verdict-${v.tone} pp`}>
      <div className="pp-top">
        <div className="pp-media">
          <ProductImage
            href={amazonButtonHref(result, "image")}
            size="page"
            src={result.image_url}
            title={name}
          />
        </div>
        <div className="pp-summary">
          <p className="verdict-title pp-title">{name}</p>
          <div className={`pp-verdict pp-verdict-${v.tone}`}>
            <span className="verdict-badge">{v.label}</span>
            <p className="verdict-blurb">
              {result.explanation?.headline ?? v.blurb}
            </p>
          </div>
          <div className="verdict-price">
            <span className="verdict-now">{formatMoney(effective, currency)}</span>
            <span className="pp-at">at Amazon.ca</span>
            <span className="verdict-conf">confidence: {assessment.confidence}</span>
          </div>
          {result.buy_url ?? result.product_url ? (
            <BuyCta
              amazonHref={amazonButtonHref(result, "checkbox")}
              amazonPriceCents={effective}
              cheapest={result.comparison?.cheapest ?? null}
              currency={currency}
              verdict={assessment.verdict}
              top
            />
          ) : null}
        </div>
      </div>

      {result.narration ? (
        <p className="verdict-narration">{result.narration}</p>
      ) : null}

      <section className="pp-history" aria-label="90-day price history">
        <h3>90-day price history</h3>
        <div className="pp-history-grid">
          <div className="pp-chart">
            {result.sparkline.length >= 2 ? (
              <div className="verdict-spark">
                <Sparkline points={result.sparkline} tone={v.tone} />
                <div className="verdict-spark-scale">
                  <span>{formatMoney(band.min, currency)}</span>
                  <span>90 days</span>
                  <span>{formatMoney(band.max, currency)}</span>
                </div>
              </div>
            ) : null}
            {result.explanation?.position ? (
              <PricePositionBar
                currency={currency}
                position={result.explanation.position}
              />
            ) : null}
          </div>
          <dl className="pp-stats">
            {band.max !== null ? (
              <div>
                <dt>Highest (90 days)</dt>
                <dd>{formatMoney(band.max, currency)}</dd>
              </div>
            ) : null}
            {band.min !== null ? (
              <div>
                <dt>Lowest (90 days)</dt>
                <dd>{formatMoney(band.min, currency)}</dd>
              </div>
            ) : null}
            {band.avg !== null ? (
              <div>
                <dt>Average</dt>
                <dd>{formatMoney(band.avg, currency)}</dd>
              </div>
            ) : null}
            <div className={`pp-stats-now pp-stats-${v.tone}`}>
              <dt>Current price</dt>
              <dd>{formatMoney(effective, currency)}</dd>
            </div>
          </dl>
        </div>
      </section>

      <DiscountChecks checks={result.explanation?.discount_checks ?? []} />

      {assessment.reasons.length > 0 ? (
        <details className="verdict-details">
          <summary>How we worked this out</summary>
          <ul className="verdict-reasons">
            {assessment.reasons.map((reason, i) => (
              <li key={i}>{reason}</li>
            ))}
          </ul>
        </details>
      ) : null}

      <OfferSpread spread={result.spread} />

      <ComparisonBlock comparison={result.comparison} />

      <AcquireBlock data={acquire} />

      <AlternativesBlock data={alternatives} />

      {result.buy_url ?? result.product_url ? (
        <BuyCta
          amazonHref={amazonButtonHref(result, "checkbox")}
          amazonPriceCents={effective}
          cheapest={result.comparison?.cheapest ?? null}
          currency={currency}
          verdict={assessment.verdict}
        />
      ) : null}

      <p className="verdict-fineprint">
        Price is a snapshot from just now — confirm at the retailer before you
        buy. SaveIQ may earn an affiliate commission if you buy through a link;
        that never changes the verdict, or which retailer we point you to.
      </p>
    </article>
  );
}

function AlertForm({ productInput }: { productInput: string }) {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<AlertState>({ kind: "idle" });

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!looksSubmittable(productInput)) {
      setState({
        kind: "error",
        message: "Paste a full amazon.ca product link (or a 10-character ASIN) above first.",
      });
      return;
    }
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
        spam. <Link href="/watchlist">See everything you&apos;re tracking →</Link>
      </p>
    );
  }

  return (
    <div className="alert-block">
      <form className="alert-form pill-search" onSubmit={(e) => void onSubmit(e)}>
        <label className="pill-search-field">
          <svg
            aria-hidden="true"
            className="pill-search-icon"
            fill="none"
            height="22"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2.2"
            viewBox="0 0 24 24"
            width="22"
          >
            <rect height="14" rx="2.5" width="18" x="3" y="5" />
            <path d="m4 7 8 6 8-6" />
          </svg>
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
          className="pill-search-chip"
          disabled={state.kind === "loading" || email.trim().length === 0}
          type="submit"
        >
          {state.kind === "loading" ? "Setting…" : "Set alert"}
        </button>
      </form>
      {state.kind === "error" ? (
        <p className="state-message" role="alert">
          {state.message}
        </p>
      ) : null}
    </div>
  );
}
