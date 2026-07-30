from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from app.core.settings import Settings
from app.services.llm_intent_contract import (
    LlmIntentParserInput,
    LlmParsedIntent,
)

MIN_LLM_INTENT_CONFIDENCE = 0.60


class LlmIntentParserClient(Protocol):
    def parse_intent(
        self,
        request: LlmIntentParserInput,
        *,
        model: str,
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """Return a raw model-shaped intent payload for schema validation."""


@dataclass(frozen=True)
class LlmIntentParserResult:
    parsed_intent: LlmParsedIntent | None
    parser_mode: str
    model: str
    fallback_required: bool
    fallback_reason: str | None


class LlmIntentParserService:
    def __init__(
        self,
        settings: Settings,
        client: LlmIntentParserClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client

    def parse(self, raw_intent: str, *, market: str = "CA") -> LlmIntentParserResult:
        parser_mode = self._settings.llm_intent_parser_mode
        model = self._settings.openai_intent_model

        if not self._settings.feature_llm_intent_parser:
            return self._fallback("feature flag disabled", parser_mode, model)

        if parser_mode == "disabled":
            return self._fallback("parser mode disabled", parser_mode, model)

        if parser_mode == "openai" and not self._settings.openai_api_key:
            return self._fallback("OpenAI API key missing", parser_mode, model)

        if self._client is None:
            return self._fallback("LLM parser client unavailable", parser_mode, model)

        try:
            request = LlmIntentParserInput(raw_intent=raw_intent, market=market)
            raw_output = self._client.parse_intent(
                request,
                model=model,
                timeout_seconds=self._settings.openai_intent_timeout_seconds,
            )
            parsed = LlmParsedIntent.model_validate(raw_output)
        except (ValidationError, ValueError, RuntimeError) as exc:
            return self._fallback(
                f"LLM parser output invalid: {exc.__class__.__name__}",
                parser_mode,
                model,
            )

        if parsed.confidence < MIN_LLM_INTENT_CONFIDENCE:
            return LlmIntentParserResult(
                parsed_intent=parsed,
                parser_mode=parser_mode,
                model=model,
                fallback_required=True,
                fallback_reason="LLM confidence below 0.60",
            )

        return LlmIntentParserResult(
            parsed_intent=parsed,
            parser_mode=parser_mode,
            model=model,
            fallback_required=False,
            fallback_reason=None,
        )

    @staticmethod
    def _fallback(
        reason: str,
        parser_mode: str,
        model: str,
    ) -> LlmIntentParserResult:
        return LlmIntentParserResult(
            parsed_intent=None,
            parser_mode=parser_mode,
            model=model,
            fallback_required=True,
            fallback_reason=reason,
        )
