"use client";

import { type FormEvent, useMemo, useState } from "react";

const QUICK_SEARCHES = ["buds", "kettle", "pack"];
const SORT_OPTIONS = [
  { label: "Lowest price", value: "price_asc" },
  { label: "Highest price", value: "price_desc" },
  { label: "Most clicked", value: "clicks_desc" },
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
  click_count: number;
  match_reasons: string[];
  ranking_reasons: string[];
};

type SearchResponse = {
  query: string | null;
  count: number;
  results: SearchResult[];
};

type RecommendationDecisionExplanation = {
  summary: string;
  matched_intent: string[];
  ranking_signals: string[];
  guardrails: string[];
};

type RecommendationResult = SearchResult & {
  decision_explanation: RecommendationDecisionExplanation;
};

type RecommendationResponse = {
  count: number;
  recommendations: RecommendationResult[];
  strategy: string;
  trace_event_id: number;
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

type ClickAnalytics = {
  total_clicks: number;
  target_counts: Record<ClickTargetType, number>;
  top_offers: {
    offer_id: number | null;
    offer_title: string | null;
    provider_source: string;
    market: string;
    click_count: number;
  }[];
  top_merchants: {
    merchant_id: number | null;
    merchant: string | null;
    provider_source: string;
    click_count: number;
  }[];
  recent_clicks: {
    id: number;
    offer_id: number | null;
    merchant: string | null;
    target_type: ClickTargetType;
    provider_source: string;
    market: string;
    created_at: string;
  }[];
};

type RecommendationTraceStep = {
  step: string;
  input: string;
  output: string;
  notes: string[];
};

type RecommendationTraceEvent = {
  id: number;
  strategy: string;
  raw_intent: string;
  parsed_intent: {
    search_query: string | null;
    has_coupon: boolean | null;
    has_cashback: boolean | null;
    freshness: string | null;
    sort: string;
  };
  result_count: number;
  recommended_offer_ids: number[];
  evaluation_trace: RecommendationTraceStep[];
  created_at: string;
};

type RecommendationTraceSummary = {
  total_traces: number;
  recent_traces: RecommendationTraceEvent[];
};

type RecommendationEvaluationCase = {
  id: string;
  status: "pass" | "fail";
  intent: string;
  count: number;
  first_source_record_id: string | null;
  first_merchant: string | null;
  trace_steps: string[];
  required_trace_steps: string[];
  failure: string | null;
};

type RecommendationEvaluationSummary = {
  status: "ok" | "failed";
  strategy: string;
  case_count: number;
  passed_count: number;
  failed_count: number;
  cases: RecommendationEvaluationCase[];
};

type RecommendationFeedbackRating = "helpful" | "not_helpful";

type RecommendationFeedbackSummary = {
  total_feedback: number;
  helpful_count: number;
  not_helpful_count: number;
  helpful_rate: number;
  unique_feedback_traces: number;
  total_recommendation_traces: number;
  trace_feedback_coverage_rate: number;
  recent_feedback: {
    id: number;
    trace_event_id: number;
    offer_id: number | null;
    offer_title: string | null;
    rating: RecommendationFeedbackRating;
    reason: string | null;
    source: string;
    provider_source: string | null;
    market: string | null;
    created_at: string;
  }[];
};

type RecommendationRetentionResult = {
  dry_run: boolean;
  keep_latest_traces: number;
  total_traces_before: number;
  total_feedback_before: number;
  trace_events_to_delete: number;
  feedback_events_to_delete: number;
  trace_events_deleted: number;
  feedback_events_deleted: number;
  retained_trace_events: number;
};

type RecommendationQualityExport = {
  report_version: string;
  exported_at: string;
  environment: string;
  staging_summary: StagingSummary;
  recommendation_evaluation: RecommendationEvaluationSummary;
  recommendation_feedback: RecommendationFeedbackSummary;
  recommendation_traces: RecommendationTraceSummary;
  retention_preview: RecommendationRetentionResult;
  notes: string[];
};

type StagingSummary = {
  counts: {
    products: number;
    listings: number;
    offers: number;
    coupons: number;
    cashback_offers: number;
    click_events: number;
    recommendation_trace_events: number;
    recommendation_feedback_events: number;
    sync_jobs: number;
    sync_errors: number;
  };
  latest_sync_job: {
    id: number;
    provider_source: string | null;
    status: string;
    started_at: string;
    completed_at: string | null;
    received_count: number;
    inserted_count: number;
    updated_count: number;
    skipped_count: number;
    rejected_count: number;
    duplicate_count: number;
    stale_count: number;
    error_count: number;
  } | null;
  recent_errors: {
    id: number;
    sync_job_id: number;
    source_record_id: string | null;
    error_code: string;
    message: string;
  }[];
};

type SyncResult = {
  job_id: number;
  provider_source: string;
  status: string;
  stats: {
    received: number;
    inserted: number;
    updated: number;
    skipped: number;
    rejected: number;
    duplicate: number;
    stale: number;
    errors: number;
  };
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

function formatRate(value: number) {
  return `${Math.round(value * 100)}%`;
}

function formatDateTime(value: string | null) {
  if (!value) {
    return "Not completed";
  }
  return new Intl.DateTimeFormat("en-CA", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
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
  const [recommendationIntent, setRecommendationIntent] = useState(
    "Find fresh wireless earbuds with a coupon"
  );
  const [results, setResults] = useState<SearchResult[]>([]);
  const [recommendations, setRecommendations] = useState<
    RecommendationResult[]
  >([]);
  const [recommendationMeta, setRecommendationMeta] =
    useState<RecommendationResponse | null>(null);
  const [selectedOffer, setSelectedOffer] = useState<OfferDetail | null>(null);
  const [adminToken, setAdminToken] = useState("");
  const [analytics, setAnalytics] = useState<ClickAnalytics | null>(null);
  const [recommendationTraces, setRecommendationTraces] =
    useState<RecommendationTraceSummary | null>(null);
  const [recommendationEvaluation, setRecommendationEvaluation] =
    useState<RecommendationEvaluationSummary | null>(null);
  const [recommendationFeedback, setRecommendationFeedback] =
    useState<RecommendationFeedbackSummary | null>(null);
  const [recommendationRetention, setRecommendationRetention] =
    useState<RecommendationRetentionResult | null>(null);
  const [recommendationQualityExport, setRecommendationQualityExport] =
    useState<RecommendationQualityExport | null>(null);
  const [feedbackStatusByOffer, setFeedbackStatusByOffer] = useState<
    Record<number, "idle" | "saving" | "helpful" | "not_helpful" | "error">
  >({});
  const [retentionKeepLatest, setRetentionKeepLatest] = useState("50");
  const [retentionConfirm, setRetentionConfirm] = useState("");
  const [stagingSummary, setStagingSummary] = useState<StagingSummary | null>(
    null
  );
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [detailStatus, setDetailStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [analyticsStatus, setAnalyticsStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [traceStatus, setTraceStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [evaluationStatus, setEvaluationStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [feedbackSummaryStatus, setFeedbackSummaryStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [retentionStatus, setRetentionStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [qualityExportStatus, setQualityExportStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [stagingStatus, setStagingStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [syncStatus, setSyncStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [status, setStatus] = useState<
    "idle" | "loading" | "ready" | "empty" | "error"
  >("idle");
  const [recommendationStatus, setRecommendationStatus] = useState<
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

  async function runRecommendations(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRecommendationStatus("loading");

    try {
      const response = await fetch("/api/recommendations", {
        body: JSON.stringify({
          intent: recommendationIntent,
          limit: 5,
        }),
        headers: {
          Accept: "application/json",
          "content-type": "application/json",
        },
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(`Recommendations failed with ${response.status}`);
      }
      const payload = (await response.json()) as RecommendationResponse;
      setRecommendations(payload.recommendations);
      setRecommendationMeta(payload);
      setRecommendationStatus(payload.count > 0 ? "ready" : "empty");
    } catch {
      setRecommendations([]);
      setRecommendationMeta(null);
      setRecommendationStatus("error");
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

  async function submitRecommendationFeedback(
    offerId: number,
    rating: RecommendationFeedbackRating
  ) {
    if (!recommendationMeta) {
      return;
    }
    setFeedbackStatusByOffer((current) => ({
      ...current,
      [offerId]: "saving",
    }));

    try {
      const response = await fetch("/api/recommendation-feedback", {
        body: JSON.stringify({
          offer_id: offerId,
          rating,
          source: "staging_ui",
          trace_event_id: recommendationMeta.trace_event_id,
        }),
        headers: {
          Accept: "application/json",
          "content-type": "application/json",
        },
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(
          `Recommendation feedback failed with ${response.status}`
        );
      }
      setFeedbackStatusByOffer((current) => ({
        ...current,
        [offerId]: rating,
      }));
    } catch {
      setFeedbackStatusByOffer((current) => ({
        ...current,
        [offerId]: "error",
      }));
    }
  }

  async function loadClickAnalytics(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setAnalyticsStatus("loading");

    try {
      const response = await fetch("/api/admin/click-analytics", {
        body: JSON.stringify({ adminToken }),
        headers: {
          Accept: "application/json",
          "content-type": "application/json",
        },
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(`Click analytics failed with ${response.status}`);
      }
      const payload = (await response.json()) as ClickAnalytics;
      setAnalytics(payload);
      setAnalyticsStatus("ready");
    } catch {
      setAnalytics(null);
      setAnalyticsStatus("error");
    }
  }

  async function loadStagingSummary(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setStagingStatus("loading");

    try {
      const response = await fetch("/api/admin/staging-summary", {
        body: JSON.stringify({ adminToken }),
        headers: {
          Accept: "application/json",
          "content-type": "application/json",
        },
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(`Staging summary failed with ${response.status}`);
      }
      const payload = (await response.json()) as StagingSummary;
      setStagingSummary(payload);
      setStagingStatus("ready");
    } catch {
      setStagingSummary(null);
      setStagingStatus("error");
    }
  }

  async function loadRecommendationTraces(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setTraceStatus("loading");

    try {
      const response = await fetch("/api/admin/recommendation-traces", {
        body: JSON.stringify({ adminToken }),
        headers: {
          Accept: "application/json",
          "content-type": "application/json",
        },
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(`Recommendation traces failed with ${response.status}`);
      }
      const payload = (await response.json()) as RecommendationTraceSummary;
      setRecommendationTraces(payload);
      setTraceStatus("ready");
    } catch {
      setRecommendationTraces(null);
      setTraceStatus("error");
    }
  }

  async function loadRecommendationEvaluation(
    event?: FormEvent<HTMLFormElement>
  ) {
    event?.preventDefault();
    setEvaluationStatus("loading");

    try {
      const response = await fetch("/api/admin/recommendation-evaluation", {
        body: JSON.stringify({ adminToken }),
        headers: {
          Accept: "application/json",
          "content-type": "application/json",
        },
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(
          `Recommendation evaluation failed with ${response.status}`
        );
      }
      const payload =
        (await response.json()) as RecommendationEvaluationSummary;
      setRecommendationEvaluation(payload);
      setEvaluationStatus("ready");
    } catch {
      setRecommendationEvaluation(null);
      setEvaluationStatus("error");
    }
  }

  async function loadRecommendationFeedback(
    event?: FormEvent<HTMLFormElement>
  ) {
    event?.preventDefault();
    setFeedbackSummaryStatus("loading");

    try {
      const response = await fetch("/api/admin/recommendation-feedback", {
        body: JSON.stringify({ adminToken }),
        headers: {
          Accept: "application/json",
          "content-type": "application/json",
        },
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(
          `Recommendation feedback failed with ${response.status}`
        );
      }
      const payload = (await response.json()) as RecommendationFeedbackSummary;
      setRecommendationFeedback(payload);
      setFeedbackSummaryStatus("ready");
    } catch {
      setRecommendationFeedback(null);
      setFeedbackSummaryStatus("error");
    }
  }

  async function refreshQualityLoop() {
    await Promise.all([
      loadRecommendationEvaluation(),
      loadRecommendationFeedback(),
      loadRecommendationTraces(),
      loadStagingSummary(),
    ]);
  }

  async function runRecommendationRetention(dryRun: boolean) {
    setRetentionStatus("loading");

    try {
      const response = await fetch(
        "/api/admin/recommendation-quality-retention",
        {
          body: JSON.stringify({
            adminToken,
            confirm: dryRun ? undefined : retentionConfirm,
            dryRun,
            keepLatestTraces: Number(retentionKeepLatest),
          }),
          headers: {
            Accept: "application/json",
            "content-type": "application/json",
          },
          method: "POST",
        }
      );
      if (!response.ok) {
        throw new Error(
          `Recommendation retention failed with ${response.status}`
        );
      }
      const payload = (await response.json()) as RecommendationRetentionResult;
      setRecommendationRetention(payload);
      setRetentionStatus("ready");
      if (!dryRun) {
        setRetentionConfirm("");
        await refreshQualityLoop();
      }
    } catch {
      setRecommendationRetention(null);
      setRetentionStatus("error");
    }
  }

  async function exportRecommendationQualityReport() {
    setQualityExportStatus("loading");

    try {
      const response = await fetch("/api/admin/recommendation-quality-export", {
        body: JSON.stringify({ adminToken }),
        headers: {
          Accept: "application/json",
          "content-type": "application/json",
        },
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(
          `Recommendation quality export failed with ${response.status}`
        );
      }
      const payload = (await response.json()) as RecommendationQualityExport;
      setRecommendationQualityExport(payload);
      setQualityExportStatus("ready");

      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const timestamp = payload.exported_at.replace(/[:.]/g, "-");
      link.href = url;
      link.download = `dealhunter-quality-report-${timestamp}.json`;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch {
      setRecommendationQualityExport(null);
      setQualityExportStatus("error");
    }
  }

  async function runMockSync() {
    setSyncStatus("loading");

    try {
      const response = await fetch("/api/admin/sync-mock", {
        body: JSON.stringify({ adminToken }),
        headers: {
          Accept: "application/json",
          "content-type": "application/json",
        },
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(`Mock sync failed with ${response.status}`);
      }
      const payload = (await response.json()) as SyncResult;
      setSyncResult(payload);
      setSyncStatus("ready");
      await loadStagingSummary();
    } catch {
      setSyncResult(null);
      setSyncStatus("error");
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

      <section
        className="recommendation-panel"
        aria-labelledby="recommendation-heading"
      >
        <div>
          <p className="eyebrow">Mock recommendations</p>
          <h2 id="recommendation-heading">Explainable offer picks</h2>
          <p className="state-message">
            Rule-based staging recommendations with visible decision signals.
          </p>
        </div>

        <form className="recommendation-form" onSubmit={runRecommendations}>
          <label className="field">
            <span>Shopping intent</span>
            <input
              value={recommendationIntent}
              onChange={(event) => setRecommendationIntent(event.target.value)}
              placeholder="Find fresh wireless earbuds with a coupon"
            />
          </label>
          <button type="submit" disabled={recommendationStatus === "loading"}>
            {recommendationStatus === "loading" ? "Thinking" : "Recommend"}
          </button>
        </form>

        {recommendationStatus === "idle" ? (
          <p className="state-message">
            Run a recommendation to see why each offer was selected.
          </p>
        ) : null}
        {recommendationStatus === "empty" ? (
          <p className="state-message">
            No recommendations found for that intent.
          </p>
        ) : null}
        {recommendationStatus === "error" ? (
          <p className="state-message">
            Recommendations are unavailable. Check API health and try again.
          </p>
        ) : null}
        {recommendationStatus === "ready" ? (
          <RecommendationList
            meta={recommendationMeta}
            recommendations={recommendations}
            feedbackStatusByOffer={feedbackStatusByOffer}
            onFeedback={submitRecommendationFeedback}
            onTrack={trackClick}
          />
        ) : null}
      </section>

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
                      <span>{result.click_count} mock clicks</span>
                      <span>{result.provider_source}</span>
                    </div>
                    <p className="match-reason">
                      Matched on {result.match_reasons.join(", ")}
                    </p>
                    <p className="ranking-reason">
                      Ranked by {result.ranking_reasons.join(", ")}
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

      <section className="admin-panel" aria-labelledby="staging-heading">
        <div className="admin-heading">
          <div>
            <p className="eyebrow">Staging data controls</p>
            <h2 id="staging-heading">Mock feed status</h2>
          </div>
          <p className="state-message">Admin only</p>
        </div>

        <form className="admin-controls" onSubmit={loadStagingSummary}>
          <label className="field">
            <span>Admin token</span>
            <input
              autoComplete="off"
              onChange={(event) => setAdminToken(event.target.value)}
              placeholder="Paste staging token"
              type="password"
              value={adminToken}
            />
          </label>
          <button type="submit" disabled={stagingStatus === "loading"}>
            {stagingStatus === "loading" ? "Refreshing" : "Refresh status"}
          </button>
          <button
            className="secondary-button"
            type="button"
            disabled={syncStatus === "loading"}
            onClick={runMockSync}
          >
            {syncStatus === "loading" ? "Seeding" : "Seed mock feed"}
          </button>
        </form>

        {stagingStatus === "idle" ? (
          <p className="state-message">
            Refresh to inspect seeded data, latest sync, and recent mock errors.
          </p>
        ) : null}
        {stagingStatus === "error" ? (
          <p className="state-message">
            Staging status unavailable. Check the admin token and API health.
          </p>
        ) : null}
        {syncStatus === "error" ? (
          <p className="state-message">
            Mock seed failed. Check the admin token and API health.
          </p>
        ) : null}
        {syncResult ? (
          <p className="state-message">
            Last seed job {syncResult.job_id}: {syncResult.status}; received{" "}
            {syncResult.stats.received}, errors {syncResult.stats.errors}.
          </p>
        ) : null}
        {stagingSummary ? (
          <StagingSummaryView summary={stagingSummary} />
        ) : null}
      </section>

      <section className="admin-panel" aria-labelledby="quality-heading">
        <div className="admin-heading">
          <div>
            <p className="eyebrow">Recommendation quality</p>
            <h2 id="quality-heading">Quality cockpit</h2>
          </div>
          <div className="admin-action-row">
            <button
              className="secondary-button"
              type="button"
              disabled={qualityExportStatus === "loading"}
              onClick={exportRecommendationQualityReport}
            >
              {qualityExportStatus === "loading"
                ? "Exporting"
                : "Export report"}
            </button>
            <button
              className="secondary-button"
              type="button"
              disabled={
                evaluationStatus === "loading" ||
                feedbackSummaryStatus === "loading" ||
                traceStatus === "loading" ||
                stagingStatus === "loading"
              }
              onClick={refreshQualityLoop}
            >
              Refresh quality loop
            </button>
          </div>
        </div>

        {recommendationEvaluation ||
        recommendationFeedback ||
        recommendationTraces ||
        stagingSummary ||
        recommendationRetention ? (
          <RecommendationQualityCockpit
            evaluation={recommendationEvaluation}
            exportReport={recommendationQualityExport}
            exportStatus={qualityExportStatus}
            feedback={recommendationFeedback}
            retention={recommendationRetention}
            stagingSummary={stagingSummary}
            traces={recommendationTraces}
          />
        ) : (
          <p className="state-message">
            Refresh to review recommendation test status, feedback coverage,
            trace volume, and retention readiness.
          </p>
        )}
      </section>

      <section className="admin-panel" aria-labelledby="analytics-heading">
        <div className="admin-heading">
          <div>
            <p className="eyebrow">Mock click analytics</p>
            <h2 id="analytics-heading">Staging click summary</h2>
          </div>
          <p className="state-message">Admin only</p>
        </div>

        <form
          className="admin-controls compact-controls"
          onSubmit={loadClickAnalytics}
        >
          <button type="submit" disabled={analyticsStatus === "loading"}>
            {analyticsStatus === "loading" ? "Refreshing" : "Refresh"}
          </button>
        </form>

        {analyticsStatus === "idle" ? (
          <p className="state-message">Refresh to load click totals.</p>
        ) : null}
        {analyticsStatus === "error" ? (
          <p className="state-message">
            Analytics unavailable. Check the admin token and API health.
          </p>
        ) : null}
        {analytics ? <ClickAnalyticsView analytics={analytics} /> : null}
      </section>

      <section className="admin-panel" aria-labelledby="evaluation-heading">
        <div className="admin-heading">
          <div>
            <p className="eyebrow">Recommendation evaluation</p>
            <h2 id="evaluation-heading">Fixture quality checks</h2>
          </div>
          <button
            className="secondary-button"
            type="button"
            disabled={
              evaluationStatus === "loading" ||
              feedbackSummaryStatus === "loading" ||
              traceStatus === "loading" ||
              stagingStatus === "loading"
            }
            onClick={refreshQualityLoop}
          >
            Refresh quality loop
          </button>
        </div>

        <form
          className="admin-controls compact-controls"
          onSubmit={loadRecommendationEvaluation}
        >
          <button type="submit" disabled={evaluationStatus === "loading"}>
            {evaluationStatus === "loading" ? "Running" : "Run evaluation"}
          </button>
        </form>

        {evaluationStatus === "idle" ? (
          <p className="state-message">
            Run the deterministic fixture suite to check recommendation quality.
          </p>
        ) : null}
        {evaluationStatus === "error" ? (
          <p className="state-message">
            Recommendation evaluation unavailable. Check the admin token and API
            health.
          </p>
        ) : null}
        {recommendationEvaluation ? (
          <RecommendationEvaluationView evaluation={recommendationEvaluation} />
        ) : null}
      </section>

      <section className="admin-panel" aria-labelledby="feedback-heading">
        <div className="admin-heading">
          <div>
            <p className="eyebrow">Recommendation feedback</p>
            <h2 id="feedback-heading">Staging quality loop</h2>
          </div>
          <p className="state-message">Admin only</p>
        </div>

        <form
          className="admin-controls compact-controls"
          onSubmit={loadRecommendationFeedback}
        >
          <button type="submit" disabled={feedbackSummaryStatus === "loading"}>
            {feedbackSummaryStatus === "loading" ? "Refreshing" : "Refresh"}
          </button>
        </form>

        {feedbackSummaryStatus === "idle" ? (
          <p className="state-message">
            Refresh to inspect Helpful and Not helpful recommendation feedback.
          </p>
        ) : null}
        {feedbackSummaryStatus === "error" ? (
          <p className="state-message">
            Recommendation feedback unavailable. Check the admin token and API
            health.
          </p>
        ) : null}
        {recommendationFeedback ? (
          <RecommendationFeedbackView feedback={recommendationFeedback} />
        ) : null}
        <RecommendationRetentionPanel
          confirm={retentionConfirm}
          keepLatest={retentionKeepLatest}
          result={recommendationRetention}
          status={retentionStatus}
          onConfirmChange={setRetentionConfirm}
          onKeepLatestChange={setRetentionKeepLatest}
          onRun={runRecommendationRetention}
        />
      </section>

      <section className="admin-panel" aria-labelledby="trace-heading">
        <div className="admin-heading">
          <div>
            <p className="eyebrow">Recommendation trace viewer</p>
            <h2 id="trace-heading">Recent recommendation traces</h2>
          </div>
          <p className="state-message">Admin only</p>
        </div>

        <form
          className="admin-controls compact-controls"
          onSubmit={loadRecommendationTraces}
        >
          <button type="submit" disabled={traceStatus === "loading"}>
            {traceStatus === "loading" ? "Refreshing" : "Refresh traces"}
          </button>
        </form>

        {traceStatus === "idle" ? (
          <p className="state-message">
            Refresh to inspect parsed intents, ranked offers, and trace steps.
          </p>
        ) : null}
        {traceStatus === "error" ? (
          <p className="state-message">
            Recommendation traces unavailable. Check the admin token and API
            health.
          </p>
        ) : null}
        {recommendationTraces ? (
          <RecommendationTraceView traces={recommendationTraces} />
        ) : null}
      </section>
    </section>
  );
}

function RecommendationQualityCockpit({
  evaluation,
  exportReport,
  exportStatus,
  feedback,
  retention,
  stagingSummary,
  traces,
}: {
  evaluation: RecommendationEvaluationSummary | null;
  exportReport: RecommendationQualityExport | null;
  exportStatus: "idle" | "loading" | "ready" | "error";
  feedback: RecommendationFeedbackSummary | null;
  retention: RecommendationRetentionResult | null;
  stagingSummary: StagingSummary | null;
  traces: RecommendationTraceSummary | null;
}) {
  const traceTotal =
    traces?.total_traces ??
    stagingSummary?.counts.recommendation_trace_events ??
    feedback?.total_recommendation_traces ??
    0;
  const feedbackTotal =
    feedback?.total_feedback ??
    stagingSummary?.counts.recommendation_feedback_events ??
    0;
  const evaluationReady = evaluation
    ? evaluation.failed_count === 0 && evaluation.passed_count > 0
    : false;
  const coverageRate = feedback?.trace_feedback_coverage_rate ?? 0;
  const retentionHasPreview = Boolean(retention?.dry_run);
  const retentionDeleteCount = retention?.trace_events_to_delete ?? 0;
  const retentionStatus = retentionHasPreview
    ? retentionDeleteCount > 0
      ? "warn"
      : "pass"
    : "neutral";

  return (
    <div className="quality-cockpit">
      <div className="quality-scoreboard">
        <QualitySignalCard
          label="Fixture suite"
          value={
            evaluation
              ? `${evaluation.passed_count}/${evaluation.case_count}`
              : "Waiting"
          }
          status={evaluationReady ? "pass" : evaluation ? "fail" : "neutral"}
          detail={
            evaluation
              ? `${evaluation.failed_count} failed cases`
              : "Run evaluation to score deterministic cases."
          }
        />
        <QualitySignalCard
          label="Feedback coverage"
          value={feedback ? formatRate(coverageRate) : "Waiting"}
          status={
            feedback
              ? coverageRate >= 0.5
                ? "pass"
                : coverageRate > 0
                  ? "warn"
                  : "fail"
              : "neutral"
          }
          detail={
            feedback
              ? `${feedback.unique_feedback_traces}/${feedback.total_recommendation_traces} traces reviewed`
              : "Refresh feedback to inspect review coverage."
          }
        />
        <QualitySignalCard
          label="Trace volume"
          value={String(traceTotal)}
          status={traceTotal > 0 ? "pass" : "neutral"}
          detail={`${feedbackTotal} feedback events recorded`}
        />
        <QualitySignalCard
          label="Retention preview"
          value={
            retention
              ? `${retention.trace_events_to_delete} old traces`
              : "Waiting"
          }
          status={retentionStatus}
          detail={
            retention
              ? `Keep latest ${retention.keep_latest_traces}; delete ${retention.feedback_events_to_delete} feedback events.`
              : "Run preview before pruning staging quality events."
          }
        />
        <QualitySignalCard
          label="Export snapshot"
          value={
            exportReport
              ? formatDateTime(exportReport.exported_at)
              : exportStatus === "error"
                ? "Failed"
                : "Waiting"
          }
          status={
            exportStatus === "ready"
              ? "pass"
              : exportStatus === "error"
                ? "fail"
                : "neutral"
          }
          detail={
            exportReport
              ? `${exportReport.report_version}; includes ${exportReport.recommendation_traces.total_traces} traces.`
              : "Download a JSON audit report before pruning or changing rules."
          }
        />
      </div>

      <div className="quality-insights">
        <section className="quality-note">
          <h3>Current readout</h3>
          <ul>
            <li>
              Evaluation{" "}
              <strong>{evaluation ? evaluation.status : "not loaded"}</strong>
            </li>
            <li>
              Feedback{" "}
              <strong>
                {feedback
                  ? `${feedback.helpful_count} helpful / ${feedback.not_helpful_count} not helpful`
                  : "not loaded"}
              </strong>
            </li>
            <li>
              Latest trace{" "}
              <strong>
                {traces?.recent_traces[0]
                  ? `#${traces.recent_traces[0].id}`
                  : "not loaded"}
              </strong>
            </li>
            <li>
              Cleanup mode{" "}
              <strong>
                {retention
                  ? retention.dry_run
                    ? "preview only"
                    : "pruned"
                  : "not previewed"}
              </strong>
            </li>
            <li>
              Last export{" "}
              <strong>
                {exportReport
                  ? formatDateTime(exportReport.exported_at)
                  : "not exported"}
              </strong>
            </li>
          </ul>
        </section>

        <section className="quality-note">
          <h3>Next check</h3>
          <p>
            {getQualityNextStep(evaluation, feedback, retention, traceTotal)}
          </p>
        </section>
      </div>
    </div>
  );
}

function QualitySignalCard({
  detail,
  label,
  status,
  value,
}: {
  detail: string;
  label: string;
  status: "pass" | "warn" | "fail" | "neutral";
  value: string;
}) {
  return (
    <div className={`quality-signal ${status}`}>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <p>{detail}</p>
    </div>
  );
}

function getQualityNextStep(
  evaluation: RecommendationEvaluationSummary | null,
  feedback: RecommendationFeedbackSummary | null,
  retention: RecommendationRetentionResult | null,
  traceTotal: number
) {
  if (!evaluation) {
    return "Run the fixture quality checks before reviewing feedback.";
  }
  if (evaluation.failed_count > 0) {
    return "Inspect failed fixture cases before changing recommendation logic.";
  }
  if (!feedback || feedback.total_feedback === 0) {
    return "Collect Helpful and Not helpful signals from the staging UI.";
  }
  if (feedback.trace_feedback_coverage_rate < 0.5) {
    return "Add feedback to more traces so coverage is easier to judge.";
  }
  if (!retention) {
    return "Preview retention once trace volume starts growing.";
  }
  if (retention.trace_events_to_delete > 0) {
    return "Review the retention preview, then prune only if old staging events are no longer needed.";
  }
  if (traceTotal === 0) {
    return "Run recommendations to create trace events.";
  }
  return "Quality checks are ready for the next recommendation gate.";
}

function StagingSummaryView({ summary }: { summary: StagingSummary }) {
  const latest = summary.latest_sync_job;

  return (
    <div className="admin-grid">
      <div className="metric-card">
        <span>Products</span>
        <strong>{summary.counts.products}</strong>
      </div>
      <div className="metric-card">
        <span>Listings</span>
        <strong>{summary.counts.listings}</strong>
      </div>
      <div className="metric-card">
        <span>Offers</span>
        <strong>{summary.counts.offers}</strong>
      </div>
      <div className="metric-card">
        <span>Clicks</span>
        <strong>{summary.counts.click_events}</strong>
      </div>
      <div className="metric-card">
        <span>Recommendation traces</span>
        <strong>{summary.counts.recommendation_trace_events ?? 0}</strong>
      </div>
      <div className="metric-card">
        <span>Recommendation feedback</span>
        <strong>{summary.counts.recommendation_feedback_events ?? 0}</strong>
      </div>

      <section className="admin-table latest-sync">
        <h3>Latest sync</h3>
        {latest ? (
          <dl className="sync-list">
            <div>
              <dt>Status</dt>
              <dd>{latest.status}</dd>
            </div>
            <div>
              <dt>Provider</dt>
              <dd>{latest.provider_source ?? "unknown"}</dd>
            </div>
            <div>
              <dt>Completed</dt>
              <dd>{formatDateTime(latest.completed_at)}</dd>
            </div>
            <div>
              <dt>Received</dt>
              <dd>{latest.received_count}</dd>
            </div>
            <div>
              <dt>Inserted</dt>
              <dd>{latest.inserted_count}</dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd>{latest.updated_count}</dd>
            </div>
            <div>
              <dt>Rejected</dt>
              <dd>{latest.rejected_count}</dd>
            </div>
            <div>
              <dt>Errors</dt>
              <dd>{latest.error_count}</dd>
            </div>
          </dl>
        ) : (
          <p className="state-message">No sync job has run yet.</p>
        )}
      </section>

      <section className="admin-table">
        <h3>Recent sync errors</h3>
        {summary.recent_errors.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Record</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {summary.recent_errors.map((error) => (
                <tr key={error.id}>
                  <td>{error.error_code}</td>
                  <td>
                    {error.source_record_id ?? `Job ${error.sync_job_id}`}
                  </td>
                  <td>{error.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="state-message">No recent sync errors.</p>
        )}
      </section>
    </div>
  );
}

function RecommendationList({
  feedbackStatusByOffer,
  meta,
  recommendations,
  onFeedback,
  onTrack,
}: {
  feedbackStatusByOffer: Record<
    number,
    "idle" | "saving" | "helpful" | "not_helpful" | "error"
  >;
  meta: RecommendationResponse | null;
  recommendations: RecommendationResult[];
  onFeedback: (offerId: number, rating: RecommendationFeedbackRating) => void;
  onTrack: (offerId: number, targetType: ClickTargetType) => void;
}) {
  return (
    <div className="recommendation-results">
      <div className="results-toolbar">
        <h3>{recommendations.length} explained recommendations</h3>
        {meta ? (
          <p>
            {meta.strategy} · trace {meta.trace_event_id}
          </p>
        ) : null}
      </div>

      <div className="recommendation-list">
        {recommendations.map((recommendation) => {
          const currentPrice =
            recommendation.sale_price_cents ?? recommendation.price_cents;
          const feedbackStatus =
            feedbackStatusByOffer[recommendation.offer_id] ?? "idle";
          const feedbackSaved =
            feedbackStatus === "helpful" || feedbackStatus === "not_helpful";
          return (
            <article
              className="recommendation-card"
              key={recommendation.offer_id}
            >
              <div className="trace-card-heading">
                <div>
                  <p className="merchant-name">{recommendation.merchant}</p>
                  <h3>{recommendation.title}</h3>
                  <p className="result-meta">
                    {[
                      recommendation.brand,
                      recommendation.category,
                      recommendation.market,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <div className="price-block">
                  <p className="price">
                    {formatMoney(currentPrice, recommendation.currency)}
                  </p>
                  {recommendation.sale_price_cents ? (
                    <p className="compare-price">
                      was{" "}
                      {formatMoney(
                        recommendation.price_cents,
                        recommendation.currency
                      )}
                    </p>
                  ) : null}
                </div>
              </div>

              <div className="explanation-block">
                <h4>Why this recommendation</h4>
                <p>{recommendation.decision_explanation.summary}</p>
                <div className="explanation-grid">
                  <ExplanationList
                    label="Matched intent"
                    values={recommendation.decision_explanation.matched_intent}
                  />
                  <ExplanationList
                    label="Ranking signals"
                    values={recommendation.decision_explanation.ranking_signals}
                  />
                  <ExplanationList
                    label="Guardrails"
                    values={recommendation.decision_explanation.guardrails}
                  />
                </div>
              </div>

              <div className="badge-row">
                <span>{recommendation.freshness_status}</span>
                {recommendation.has_coupon ? <span>Coupon</span> : null}
                {recommendation.has_cashback ? <span>Cashback</span> : null}
                <span>{recommendation.provider_source}</span>
              </div>
              {recommendation.product_url ? (
                <a
                  className="source-link"
                  href={recommendation.product_url}
                  onClick={() =>
                    void onTrack(recommendation.offer_id, "product")
                  }
                  rel="noreferrer"
                  target="_blank"
                >
                  Open mock product URL
                </a>
              ) : null}
              <div className="feedback-actions">
                <span>
                  {feedbackStatus === "saving"
                    ? "Saving feedback"
                    : feedbackSaved
                      ? `Marked ${feedbackStatus.replace("_", " ")}`
                      : feedbackStatus === "error"
                        ? "Feedback failed"
                        : "Was this useful?"}
                </span>
                <button
                  className="secondary-button"
                  type="button"
                  disabled={feedbackStatus === "saving"}
                  onClick={() =>
                    void onFeedback(recommendation.offer_id, "helpful")
                  }
                >
                  Helpful
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  disabled={feedbackStatus === "saving"}
                  onClick={() =>
                    void onFeedback(recommendation.offer_id, "not_helpful")
                  }
                >
                  Not helpful
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

function ExplanationList({
  label,
  values,
}: {
  label: string;
  values: string[];
}) {
  return (
    <div>
      <strong>{label}</strong>
      <ul>
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </div>
  );
}

function RecommendationFeedbackView({
  feedback,
}: {
  feedback: RecommendationFeedbackSummary;
}) {
  return (
    <div className="feedback-dashboard">
      <div className="admin-grid evaluation-metrics">
        <div className="metric-card">
          <span>Total feedback</span>
          <strong>{feedback.total_feedback}</strong>
        </div>
        <div className="metric-card">
          <span>Helpful rate</span>
          <strong>{formatRate(feedback.helpful_rate)}</strong>
        </div>
        <div className="metric-card">
          <span>Trace coverage</span>
          <strong>{formatRate(feedback.trace_feedback_coverage_rate)}</strong>
        </div>
        <div className="metric-card">
          <span>Feedback traces</span>
          <strong>
            {feedback.unique_feedback_traces}/
            {feedback.total_recommendation_traces}
          </strong>
        </div>
      </div>

      <div className="feedback-split">
        <div className="metric-card feedback-sentiment helpful">
          <span>Helpful</span>
          <strong>{feedback.helpful_count}</strong>
          <p>Accepted recommendation picks from staging reviewers.</p>
        </div>
        <div className="metric-card feedback-sentiment not-helpful">
          <span>Not helpful</span>
          <strong>{feedback.not_helpful_count}</strong>
          <p>Review signals to inspect before real AI scoring.</p>
        </div>
      </div>

      <section className="quality-note">
        <h3>Feedback loop status</h3>
        <p>
          This panel connects recommendation traces, reviewer feedback, and
          fixture evaluation. It is staging-only and does not train or call a
          live AI model yet.
        </p>
      </section>

      <section className="admin-table recent-clicks">
        <h3>Recent feedback</h3>
        {feedback.recent_feedback.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Rating</th>
                <th>Offer</th>
                <th>Trace</th>
                <th>Recorded</th>
              </tr>
            </thead>
            <tbody>
              {feedback.recent_feedback.map((event) => (
                <tr key={event.id}>
                  <td>
                    <span
                      className={
                        event.rating === "helpful"
                          ? "status-pill pass"
                          : "status-pill fail"
                      }
                    >
                      {event.rating.replace("_", " ")}
                    </span>
                  </td>
                  <td>{event.offer_title ?? `Offer ${event.offer_id}`}</td>
                  <td>
                    {event.trace_event_id} · {event.provider_source ?? "n/a"} ·{" "}
                    {event.market ?? "n/a"}
                  </td>
                  <td>{formatDateTime(event.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="state-message">No recommendation feedback yet.</p>
        )}
      </section>
    </div>
  );
}

function RecommendationRetentionPanel({
  confirm,
  keepLatest,
  result,
  status,
  onConfirmChange,
  onKeepLatestChange,
  onRun,
}: {
  confirm: string;
  keepLatest: string;
  result: RecommendationRetentionResult | null;
  status: "idle" | "loading" | "ready" | "error";
  onConfirmChange: (value: string) => void;
  onKeepLatestChange: (value: string) => void;
  onRun: (dryRun: boolean) => void;
}) {
  const canPrune = confirm === "DELETE_STAGING_QUALITY_EVENTS";

  return (
    <section className="retention-panel" aria-labelledby="retention-heading">
      <div>
        <p className="eyebrow">Retention controls</p>
        <h3 id="retention-heading">Staging quality event cleanup</h3>
        <p className="state-message">
          Preview old recommendation traces and feedback before pruning. This
          only affects staging review events.
        </p>
      </div>

      <div className="retention-controls">
        <label className="field compact-field">
          <span>Keep latest traces</span>
          <input
            min="0"
            max="500"
            onChange={(event) => onKeepLatestChange(event.target.value)}
            type="number"
            value={keepLatest}
          />
        </label>
        <button
          className="secondary-button"
          type="button"
          disabled={status === "loading"}
          onClick={() => onRun(true)}
        >
          {status === "loading" ? "Checking" : "Preview cleanup"}
        </button>
      </div>

      <div className="retention-danger">
        <label className="field">
          <span>Confirm phrase</span>
          <input
            autoComplete="off"
            onChange={(event) => onConfirmChange(event.target.value)}
            placeholder="DELETE_STAGING_QUALITY_EVENTS"
            value={confirm}
          />
        </label>
        <button
          type="button"
          disabled={status === "loading" || !canPrune}
          onClick={() => onRun(false)}
        >
          Prune old events
        </button>
      </div>

      {status === "error" ? (
        <p className="state-message">
          Retention request failed. Check the admin token, confirm phrase, and
          API health.
        </p>
      ) : null}
      {result ? (
        <div className="retention-result">
          <div>
            <span>{result.dry_run ? "Preview" : "Pruned"}</span>
            <strong>{result.trace_events_to_delete}</strong>
            <p>trace events selected</p>
          </div>
          <div>
            <span>Feedback</span>
            <strong>{result.feedback_events_to_delete}</strong>
            <p>feedback events selected</p>
          </div>
          <div>
            <span>Retained</span>
            <strong>{result.retained_trace_events}</strong>
            <p>trace events after policy</p>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function ClickAnalyticsView({ analytics }: { analytics: ClickAnalytics }) {
  return (
    <div className="admin-grid">
      <div className="metric-card">
        <span>Total clicks</span>
        <strong>{analytics.total_clicks}</strong>
      </div>
      <div className="metric-card">
        <span>Product clicks</span>
        <strong>{analytics.target_counts.product ?? 0}</strong>
      </div>
      <div className="metric-card">
        <span>Affiliate clicks</span>
        <strong>{analytics.target_counts.affiliate ?? 0}</strong>
      </div>

      <section className="admin-table">
        <h3>Top offers</h3>
        {analytics.top_offers.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Offer</th>
                <th>Source</th>
                <th>Clicks</th>
              </tr>
            </thead>
            <tbody>
              {analytics.top_offers.map((offer) => (
                <tr key={`${offer.offer_id}-${offer.provider_source}`}>
                  <td>{offer.offer_title ?? `Offer ${offer.offer_id}`}</td>
                  <td>
                    {offer.provider_source} · {offer.market}
                  </td>
                  <td>{offer.click_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="state-message">No tracked clicks yet.</p>
        )}
      </section>

      <section className="admin-table">
        <h3>Top merchants</h3>
        {analytics.top_merchants.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Merchant</th>
                <th>Source</th>
                <th>Clicks</th>
              </tr>
            </thead>
            <tbody>
              {analytics.top_merchants.map((merchant) => (
                <tr key={`${merchant.merchant_id}-${merchant.provider_source}`}>
                  <td>
                    {merchant.merchant ?? `Merchant ${merchant.merchant_id}`}
                  </td>
                  <td>{merchant.provider_source}</td>
                  <td>{merchant.click_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="state-message">No merchant clicks yet.</p>
        )}
      </section>

      <section className="admin-table recent-clicks">
        <h3>Recent clicks</h3>
        {analytics.recent_clicks.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Target</th>
                <th>Merchant</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {analytics.recent_clicks.map((click) => (
                <tr key={click.id}>
                  <td>{click.target_type}</td>
                  <td>{click.merchant ?? `Offer ${click.offer_id}`}</td>
                  <td>
                    {click.provider_source} · {click.market}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="state-message">No recent clicks yet.</p>
        )}
      </section>
    </div>
  );
}

function RecommendationEvaluationView({
  evaluation,
}: {
  evaluation: RecommendationEvaluationSummary;
}) {
  return (
    <div className="evaluation-viewer">
      <div className="admin-grid evaluation-metrics">
        <div className="metric-card">
          <span>Status</span>
          <strong>{evaluation.status}</strong>
        </div>
        <div className="metric-card">
          <span>Cases</span>
          <strong>{evaluation.case_count}</strong>
        </div>
        <div className="metric-card">
          <span>Passed</span>
          <strong>{evaluation.passed_count}</strong>
        </div>
        <div className="metric-card">
          <span>Failed</span>
          <strong>{evaluation.failed_count}</strong>
        </div>
      </div>

      <section className="admin-table evaluation-table">
        <h3>{evaluation.strategy}</h3>
        <table>
          <thead>
            <tr>
              <th>Case</th>
              <th>Expected behavior</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {evaluation.cases.map((testCase) => (
              <tr key={testCase.id}>
                <td>
                  <strong>{testCase.id}</strong>
                  <span>{testCase.intent}</span>
                </td>
                <td>
                  <span>
                    Trace: {testCase.required_trace_steps.join(" -> ")}
                  </span>
                  <span>
                    First: {testCase.first_source_record_id ?? "none"}
                  </span>
                </td>
                <td>
                  <span
                    className={
                      testCase.status === "pass"
                        ? "status-pill pass"
                        : "status-pill fail"
                    }
                  >
                    {testCase.status}
                  </span>
                  <span>
                    {testCase.status === "pass"
                      ? `${testCase.count} results · ${
                          testCase.first_merchant ?? "unknown"
                        }`
                      : testCase.failure}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function RecommendationTraceView({
  traces,
}: {
  traces: RecommendationTraceSummary;
}) {
  return (
    <div className="trace-viewer">
      <div className="metric-card">
        <span>Total traces</span>
        <strong>{traces.total_traces}</strong>
      </div>

      {traces.recent_traces.length > 0 ? (
        <div className="trace-list">
          {traces.recent_traces.map((trace) => (
            <article className="trace-card" key={trace.id}>
              <div className="trace-card-heading">
                <div>
                  <p className="merchant-name">Trace {trace.id}</p>
                  <h3>{trace.raw_intent}</h3>
                  <p className="result-meta">
                    {trace.strategy} · {formatDateTime(trace.created_at)}
                  </p>
                </div>
                <div className="price-block">
                  <p className="price">{trace.result_count}</p>
                  <p className="compare-price">results</p>
                </div>
              </div>

              <dl className="trace-intent">
                <div>
                  <dt>Query</dt>
                  <dd>{trace.parsed_intent.search_query ?? "none"}</dd>
                </div>
                <div>
                  <dt>Sort</dt>
                  <dd>{trace.parsed_intent.sort}</dd>
                </div>
                <div>
                  <dt>Coupon</dt>
                  <dd>{String(trace.parsed_intent.has_coupon ?? "any")}</dd>
                </div>
                <div>
                  <dt>Cashback</dt>
                  <dd>{String(trace.parsed_intent.has_cashback ?? "any")}</dd>
                </div>
                <div>
                  <dt>Freshness</dt>
                  <dd>{trace.parsed_intent.freshness ?? "any"}</dd>
                </div>
                <div>
                  <dt>Offer IDs</dt>
                  <dd>{trace.recommended_offer_ids.join(", ") || "none"}</dd>
                </div>
              </dl>

              <ol className="trace-steps">
                {trace.evaluation_trace.map((step) => (
                  <li key={`${trace.id}-${step.step}`}>
                    <div>
                      <strong>{step.step}</strong>
                      <span>{step.output}</span>
                    </div>
                    <p>{step.notes.join(", ")}</p>
                  </li>
                ))}
              </ol>
            </article>
          ))}
        </div>
      ) : (
        <p className="state-message">No recommendation traces yet.</p>
      )}
    </div>
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
          <p className="result-meta">{offer.click_count} mock clicks</p>
          <p className="ranking-reason">
            Ranked by {offer.ranking_reasons.join(", ")}
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
