from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import TypedDict

from sqlalchemy.orm import Session

from app.models import RecommendationTraceEvent
from app.services.recommendation_versions import (
    RECOMMENDATION_FIXTURE_SET_VERSION,
    RECOMMENDATION_INTENT_PARSER_VERSION,
    RECOMMENDATION_RANKER_VERSION,
    RECOMMENDATION_RULE_VERSION,
    RECOMMENDATION_STRATEGY,
)
from app.services.search import SearchFilters, SearchResultRow, search_offers

MAX_RECOMMENDATION_LIMIT = 10
DEFAULT_RECOMMENDATION_LIMIT = 5


@dataclass(frozen=True)
class RecommendationIntent:
    raw_intent: str
    search_query: str | None
    has_coupon: bool | None
    has_cashback: bool | None
    freshness: str | None
    sort: str


class RecommendationTraceStep(TypedDict):
    step: str
    input: str
    output: str
    notes: list[str]


class RecommendationDecisionExplanation(TypedDict):
    summary: str
    matched_intent: list[str]
    ranking_signals: list[str]
    guardrails: list[str]


class RecommendationOfferResult(SearchResultRow):
    decision_explanation: RecommendationDecisionExplanation


class RecommendationResult(TypedDict):
    strategy: str
    rule_version: str
    intent_parser_version: str
    ranker_version: str
    intent: RecommendationIntent
    trace_event_id: int
    trace: list[RecommendationTraceStep]
    results: list[RecommendationOfferResult]


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOP_TERMS = {
    "a",
    "an",
    "and",
    "available",
    "back",
    "below",
    "best",
    "buy",
    "cash",
    "cashback",
    "cheap",
    "cheapest",
    "coupon",
    "deal",
    "deals",
    "discount",
    "expensive",
    "find",
    "for",
    "fresh",
    "give",
    "highest",
    "latest",
    "less",
    "me",
    "new",
    "offer",
    "offers",
    "popular",
    "premium",
    "promo",
    "recent",
    "show",
    "than",
    "the",
    "to",
    "trending",
    "under",
    "want",
    "with",
}


def _tokens(value: str) -> list[str]:
    return _TOKEN_PATTERN.findall(value.casefold())


def _intent_search_query(tokens: list[str]) -> str | None:
    product_terms = [
        token
        for token in tokens
        if token not in _STOP_TERMS and not token.isdigit() and len(token) >= 3
    ]
    if not product_terms:
        return None
    return " ".join(product_terms)


def parse_recommendation_intent(raw_intent: str) -> RecommendationIntent:
    tokens = _tokens(raw_intent)
    token_set = set(tokens)
    has_coupon = True if token_set & {"coupon", "promo", "discount"} else None
    has_cashback = True if {"cash", "back"}.issubset(token_set) else None
    if "cashback" in token_set:
        has_cashback = True
    freshness = "fresh" if token_set & {"fresh", "latest", "new", "recent"} else None

    if token_set & {"popular", "trending", "clicked"}:
        sort = "clicks_desc"
    elif token_set & {"premium", "expensive", "highest"}:
        sort = "price_desc"
    else:
        sort = "price_asc"

    return RecommendationIntent(
        raw_intent=raw_intent,
        search_query=_intent_search_query(tokens),
        has_coupon=has_coupon,
        has_cashback=has_cashback,
        freshness=freshness,
        sort=sort,
    )


def _trace_intent(intent: RecommendationIntent) -> RecommendationTraceStep:
    filters = [
        f"query={intent.search_query!r}",
        f"has_coupon={intent.has_coupon}",
        f"has_cashback={intent.has_cashback}",
        f"freshness={intent.freshness}",
        f"sort={intent.sort}",
    ]
    return {
        "step": "parse_intent",
        "input": intent.raw_intent,
        "output": ", ".join(filters),
        "notes": [
            "rule-based parser",
            RECOMMENDATION_INTENT_PARSER_VERSION,
            "no model call",
        ],
    }


def _trace_retrieval(filters: SearchFilters, result_count: int) -> RecommendationTraceStep:
    return {
        "step": "retrieve_candidates",
        "input": f"stored offers limit={filters.limit}",
        "output": f"{result_count} candidates",
        "notes": ["uses normalized database records", "no web scraping"],
    }


def _trace_ranking(intent: RecommendationIntent, result_count: int) -> RecommendationTraceStep:
    return {
        "step": "rank_candidates",
        "input": intent.sort,
        "output": f"{result_count} ranked recommendations",
        "notes": [
            "reuses transparent search ranking reasons",
            "deterministic mock strategy",
            RECOMMENDATION_RANKER_VERSION,
        ],
    }


def _decision_explanation(
    row: SearchResultRow,
    intent: RecommendationIntent,
) -> RecommendationDecisionExplanation:
    matched_intent = list(row["match_reasons"])
    if intent.has_coupon is True and row["has_coupon"]:
        matched_intent.append("coupon requested and available")
    if intent.has_cashback is True and row["has_cashback"]:
        matched_intent.append("cashback requested and available")
    if intent.freshness == row["freshness_status"]:
        matched_intent.append(f"{intent.freshness} freshness requested")

    ranking_signals = list(row["ranking_reasons"])
    guardrails = [
        "uses stored normalized mock offers",
        "no model call",
        "no web scraping",
        "no real affiliate network request",
    ]
    current_price = row["sale_price_cents"] or row["price_cents"]
    summary_parts = [
        f"{row['merchant']} matched {intent.search_query or 'the broad intent'}",
        f"ranked by {intent.sort}",
        f"current price {current_price / 100:.2f} {row['currency']}",
    ]
    if row["has_coupon"]:
        summary_parts.append("coupon available")
    if row["has_cashback"]:
        summary_parts.append("cashback available")

    return {
        "summary": "; ".join(summary_parts),
        "matched_intent": matched_intent,
        "ranking_signals": ranking_signals,
        "guardrails": guardrails,
    }


def recommend_offers(
    db: Session,
    raw_intent: str,
    limit: int = DEFAULT_RECOMMENDATION_LIMIT,
) -> RecommendationResult:
    bounded_limit = max(1, min(limit, MAX_RECOMMENDATION_LIMIT))
    intent = parse_recommendation_intent(raw_intent)
    filters = SearchFilters(
        query=intent.search_query,
        has_coupon=intent.has_coupon,
        has_cashback=intent.has_cashback,
        freshness=intent.freshness,
        sort=intent.sort,
        limit=bounded_limit,
    )
    search_results = search_offers(db, filters)
    results: list[RecommendationOfferResult] = [
        {
            **row,
            "decision_explanation": _decision_explanation(row, intent),
        }
        for row in search_results
    ]
    strategy = RECOMMENDATION_STRATEGY
    trace = [
        _trace_intent(intent),
        _trace_retrieval(filters, len(search_results)),
        _trace_ranking(intent, len(search_results)),
    ]
    trace_event = RecommendationTraceEvent(
        strategy=strategy,
        rule_version=RECOMMENDATION_RULE_VERSION,
        intent_parser_version=RECOMMENDATION_INTENT_PARSER_VERSION,
        ranker_version=RECOMMENDATION_RANKER_VERSION,
        fixture_set_version=RECOMMENDATION_FIXTURE_SET_VERSION,
        raw_intent=raw_intent,
        parsed_intent=asdict(intent),
        result_count=len(results),
        recommended_offer_ids=[result["offer_id"] for result in results],
        trace=trace,
    )
    db.add(trace_event)
    db.commit()
    db.refresh(trace_event)
    return {
        "strategy": strategy,
        "rule_version": RECOMMENDATION_RULE_VERSION,
        "intent_parser_version": RECOMMENDATION_INTENT_PARSER_VERSION,
        "ranker_version": RECOMMENDATION_RANKER_VERSION,
        "intent": intent,
        "trace_event_id": trace_event.id,
        "trace": trace,
        "results": results,
    }
