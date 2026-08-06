"""LLM provider contracts for Gate 6B AI router."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.services.llm_intent_contract import LlmIntentParserInput


@dataclass(frozen=True)
class ProviderUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class ProviderParseResult:
    provider: str
    model: str
    payload: dict[str, Any]
    usage: ProviderUsage
    latency_ms: float


class BaseLLMProvider(Protocol):
    """Abstract intent-parser provider used by the AI router."""

    name: str

    def is_configured(self) -> bool:
        """Return True when this provider can make a request."""

    def parse_intent(
        self,
        request: LlmIntentParserInput,
        *,
        model: str,
        timeout_seconds: float,
    ) -> ProviderParseResult:
        """Return schema-shaped intent JSON plus usage/latency metadata."""
