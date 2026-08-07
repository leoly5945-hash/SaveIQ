"""OpenAI intent-parser provider for Gate 6B."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any, Protocol

from app.services.llm_intent_contract import (
    LLM_INTENT_ALLOWED_SORTS,
    LLM_INTENT_GUARDRAILS,
    LLM_INTENT_OUTPUT_SCHEMA_NAME,
    LLM_INTENT_PROMPT_VERSION,
    LlmIntentParserInput,
)
from app.services.router.providers.base import ProviderParseResult, ProviderUsage

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


class JsonHttpTransport(Protocol):
    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """Send JSON and return a decoded JSON object."""


class UrllibJsonHttpTransport:
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
            raise RuntimeError("OpenAI provider request failed") from exc
        try:
            decoded = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI provider returned invalid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise RuntimeError("OpenAI provider returned a non-object response")
        return decoded


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        api_key: str | None,
        transport: JsonHttpTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._transport = transport or UrllibJsonHttpTransport()

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def parse_intent(
        self,
        request: LlmIntentParserInput,
        *,
        model: str,
        timeout_seconds: float,
    ) -> ProviderParseResult:
        if not self._api_key:
            raise RuntimeError("OpenAI provider is not configured")
        started = time.perf_counter()
        response = self._transport.post_json(
            OPENAI_CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            payload=_build_openai_payload(request, model=model),
            timeout_seconds=timeout_seconds,
        )
        payload = _extract_openai_content(response)
        usage = _extract_openai_usage(response)
        latency_ms = (time.perf_counter() - started) * 1000.0
        return ProviderParseResult(
            provider=self.name,
            model=model,
            payload=dict(payload),
            usage=usage,
            latency_ms=latency_ms,
        )


def _build_openai_payload(request: LlmIntentParserInput, *, model: str) -> dict[str, Any]:
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
                "schema": _intent_response_schema(),
            },
        },
    }


def _intent_response_schema() -> dict[str, Any]:
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


def _extract_openai_content(response: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        choices = response["choices"]
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenAI provider response missing choices")
        first_choice = choices[0]
        if not isinstance(first_choice, Mapping):
            raise RuntimeError("OpenAI provider choice is not an object")
        message = first_choice["message"]
        if not isinstance(message, Mapping):
            raise RuntimeError("OpenAI provider message is not an object")
        content = message["content"]
        if not isinstance(content, str):
            raise RuntimeError("OpenAI provider content is not a string")
        parsed = json.loads(content)
    except KeyError as exc:
        raise RuntimeError("OpenAI provider response is missing fields") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI provider content is invalid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise RuntimeError("OpenAI provider content is not an object")
    return parsed


def _extract_openai_usage(response: Mapping[str, Any]) -> ProviderUsage:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return ProviderUsage()
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    return ProviderUsage(
        prompt_tokens=int(prompt or 0),
        completion_tokens=int(completion or 0),
    )
