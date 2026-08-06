"""Mock LLM provider for Gate 6B (no network, no API keys)."""

from __future__ import annotations

import time

from app.services.llm_intent_contract import LlmIntentParserInput
from app.services.router.providers.base import ProviderParseResult, ProviderUsage


class MockProvider:
    name = "mock"

    def is_configured(self) -> bool:
        return True

    def parse_intent(
        self,
        request: LlmIntentParserInput,
        *,
        model: str,
        timeout_seconds: float,
    ) -> ProviderParseResult:
        started = time.perf_counter()
        query = request.raw_intent.strip()
        search_query = " ".join(query.split()[:6])[:120] or "mock search"
        payload = {
            "search_query": search_query,
            "has_coupon": "coupon" in query.lower(),
            "has_cashback": "cashback" in query.lower(),
            "freshness": "fresh" if "fresh" in query.lower() else None,
            "sort": "price_asc",
            "confidence": 0.88,
            "reasoning_summary": "Mock provider parsed a constrained shopping intent.",
            "fallback_reason": None,
        }
        latency_ms = (time.perf_counter() - started) * 1000.0
        return ProviderParseResult(
            provider=self.name,
            model=model or "mock-intent-model",
            payload=payload,
            usage=ProviderUsage(prompt_tokens=24, completion_tokens=16),
            latency_ms=latency_ms,
        )
