"""Anthropic intent-parser provider for Gate 6B."""

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
    LLM_INTENT_PROMPT_VERSION,
    LlmIntentParserInput,
)
from app.services.router.providers.base import ProviderParseResult, ProviderUsage
from app.services.router.providers.openai_provider import _intent_response_schema

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


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
            raise RuntimeError("Anthropic provider request failed") from exc
        try:
            decoded = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Anthropic provider returned invalid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise RuntimeError("Anthropic provider returned a non-object response")
        return decoded


class AnthropicProvider:
    name = "anthropic"

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
            raise RuntimeError("Anthropic provider is not configured")
        started = time.perf_counter()
        response = self._transport.post_json(
            ANTHROPIC_MESSAGES_URL,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "Content-Type": "application/json",
            },
            payload=_build_anthropic_payload(request, model=model),
            timeout_seconds=timeout_seconds,
        )
        payload = _extract_anthropic_content(response)
        usage = _extract_anthropic_usage(response)
        latency_ms = (time.perf_counter() - started) * 1000.0
        return ProviderParseResult(
            provider=self.name,
            model=model,
            payload=dict(payload),
            usage=usage,
            latency_ms=latency_ms,
        )


def _build_anthropic_payload(request: LlmIntentParserInput, *, model: str) -> dict[str, Any]:
    schema = _intent_response_schema()
    return {
        "model": model,
        "max_tokens": 512,
        "system": (
            "You are SaveIQ's constrained shopping-intent parser. "
            "Return only valid JSON matching the supplied schema. "
            "Do not browse, call tools, invent merchants, invent products, "
            "invent prices, invent coupons, or invent cashback."
        ),
        "messages": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "prompt_version": LLM_INTENT_PROMPT_VERSION,
                        "raw_intent": request.raw_intent,
                        "market": request.market,
                        "locale": request.locale,
                        "allowed_sorts": list(LLM_INTENT_ALLOWED_SORTS),
                        "guardrails": list(LLM_INTENT_GUARDRAILS),
                        "output_schema": schema,
                    },
                    sort_keys=True,
                ),
            }
        ],
    }


def _extract_anthropic_content(response: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        content = response["content"]
        if not isinstance(content, list) or not content:
            raise RuntimeError("Anthropic provider response missing content")
        first = content[0]
        if not isinstance(first, Mapping):
            raise RuntimeError("Anthropic provider content item is not an object")
        text = first.get("text")
        if not isinstance(text, str):
            raise RuntimeError("Anthropic provider content text is not a string")
        parsed = json.loads(text)
    except KeyError as exc:
        raise RuntimeError("Anthropic provider response is missing fields") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Anthropic provider content is invalid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise RuntimeError("Anthropic provider content is not an object")
    return parsed


def _extract_anthropic_usage(response: Mapping[str, Any]) -> ProviderUsage:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return ProviderUsage()
    return ProviderUsage(
        prompt_tokens=int(usage.get("input_tokens") or 0),
        completion_tokens=int(usage.get("output_tokens") or 0),
    )
