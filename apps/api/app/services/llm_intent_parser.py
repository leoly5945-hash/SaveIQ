from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from app.core.settings import Settings
from app.services.llm_intent_contract import (
    LLM_INTENT_ALLOWED_SORTS,
    LLM_INTENT_GUARDRAILS,
    LLM_INTENT_OUTPUT_SCHEMA_NAME,
    LLM_INTENT_PROMPT_VERSION,
    LlmIntentParserInput,
    LlmParsedIntent,
)
from app.services.router.contract import AI_ROUTER_FALLBACK_MODEL, RouteRequest
from app.services.router.mock_router import MockRouter

MIN_LLM_INTENT_CONFIDENCE = 0.60
LLM_INTENT_RUNTIME_PARSER_VERSION = "llm-intent-parser-v0"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"

logger = logging.getLogger(__name__)


class LlmIntentParserClient(Protocol):
    def parse_intent(
        self,
        request: LlmIntentParserInput,
        *,
        model: str,
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """Return a raw model-shaped intent payload for schema validation."""


class OpenAIHttpTransport(Protocol):
    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """Send JSON and return a decoded JSON object."""


class UrllibOpenAIHttpTransport:
    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=dict(headers),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            raise RuntimeError("OpenAI intent parser request failed") from exc

        try:
            decoded = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI intent parser returned invalid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise RuntimeError("OpenAI intent parser returned a non-object response")
        return decoded


class OpenAIIntentParserClient:
    def __init__(
        self,
        api_key: str,
        transport: OpenAIHttpTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._transport = transport or UrllibOpenAIHttpTransport()

    def parse_intent(
        self,
        request: LlmIntentParserInput,
        *,
        model: str,
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        response = self._transport.post_json(
            OPENAI_CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            payload=_build_openai_chat_payload(request, model=model),
            timeout_seconds=timeout_seconds,
        )
        return _extract_openai_intent_payload(response)


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
        router: MockRouter | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._router = router or MockRouter(settings)

    def parse(self, raw_intent: str, *, market: str = "CA") -> LlmIntentParserResult:
        parser_mode = self._settings.llm_intent_parser_mode
        model = self._settings.openai_intent_model

        if self._settings.feature_ai_router:
            selected_model = self._route_selected_model(raw_intent)
            logger.info("AI router selected_model=%s", selected_model)
            if selected_model == AI_ROUTER_FALLBACK_MODEL:
                return self._fallback(
                    f"router selected {AI_ROUTER_FALLBACK_MODEL}",
                    parser_mode,
                    selected_model,
                )
            model = selected_model

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

    def _route_selected_model(self, raw_intent: str) -> str:
        try:
            decision = self._router.route(
                RouteRequest(
                    query_text=raw_intent,
                    intent_type="recommendation",
                )
            )
            logger.info(
                "AI router decision selected_model=%s complexity=%s reason=%s",
                decision.selected_model,
                decision.complexity.value,
                decision.reason,
            )
            return decision.selected_model or AI_ROUTER_FALLBACK_MODEL
        except Exception as exc:  # noqa: BLE001 - router must never break parsing
            logger.warning(
                "AI router failed; falling back to %s (%s)",
                AI_ROUTER_FALLBACK_MODEL,
                exc.__class__.__name__,
            )
            return AI_ROUTER_FALLBACK_MODEL

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


def build_llm_intent_parser_service(settings: Settings) -> LlmIntentParserService:
    client: LlmIntentParserClient | None = None
    if (
        settings.feature_llm_intent_parser
        and settings.llm_intent_parser_mode == "openai"
        and settings.openai_api_key
    ):
        client = OpenAIIntentParserClient(settings.openai_api_key)
    return LlmIntentParserService(settings, client, router=MockRouter(settings))


def _build_openai_chat_payload(
    request: LlmIntentParserInput,
    *,
    model: str,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are DealHunter's constrained shopping-intent parser. "
                    "Return only valid JSON for the supplied schema. "
                    "Do not browse, call tools, invent merchants, invent products, "
                    "invent prices, invent coupons, or invent cashback."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "prompt_version": LLM_INTENT_PROMPT_VERSION,
                        "raw_intent": request.raw_intent,
                        "market": request.market,
                        "locale": request.locale,
                        "allowed_sorts": list(request.allowed_sorts),
                        "guardrails": list(LLM_INTENT_GUARDRAILS),
                    },
                    sort_keys=True,
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": LLM_INTENT_OUTPUT_SCHEMA_NAME.replace(".", "_"),
                "strict": True,
                "schema": _openai_intent_response_schema(),
            },
        },
    }


def _openai_intent_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "search_query",
            "has_coupon",
            "has_cashback",
            "freshness",
            "sort",
            "confidence",
            "reasoning_summary",
            "fallback_reason",
        ],
        "properties": {
            "search_query": {
                "anyOf": [{"type": "string", "maxLength": 120}, {"type": "null"}],
            },
            "has_coupon": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
            "has_cashback": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
            "freshness": {"anyOf": [{"type": "string", "enum": ["fresh"]}, {"type": "null"}]},
            "sort": {"type": "string", "enum": list(LLM_INTENT_ALLOWED_SORTS)},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reasoning_summary": {"type": "string", "minLength": 1, "maxLength": 240},
            "fallback_reason": {
                "anyOf": [{"type": "string", "maxLength": 160}, {"type": "null"}],
            },
        },
    }


def _extract_openai_intent_payload(response: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        choices = response["choices"]
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenAI intent parser response missing choices")
        first_choice = choices[0]
        if not isinstance(first_choice, Mapping):
            raise RuntimeError("OpenAI intent parser choice is not an object")
        message = first_choice["message"]
        if not isinstance(message, Mapping):
            raise RuntimeError("OpenAI intent parser message is not an object")
        content = message["content"]
        if not isinstance(content, str):
            raise RuntimeError("OpenAI intent parser content is not a string")
        parsed = json.loads(content)
    except KeyError as exc:
        raise RuntimeError("OpenAI intent parser response is missing fields") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI intent parser content is invalid JSON") from exc

    if not isinstance(parsed, Mapping):
        raise RuntimeError("OpenAI intent parser content is not an object")
    return parsed
