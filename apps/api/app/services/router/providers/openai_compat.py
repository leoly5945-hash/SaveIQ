"""Shared OpenAI-compatible HTTP helpers for Gate 6B/9 providers."""

from __future__ import annotations

import json
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
from app.services.router.providers.base import ProviderUsage


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
            raise RuntimeError("LLM provider request failed") from exc
        try:
            decoded = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("LLM provider returned invalid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise RuntimeError("LLM provider returned a non-object response")
        return decoded


def build_chat_completions_payload(
    request: LlmIntentParserInput,
    *,
    model: str,
    include_json_schema: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are SaveIQ's constrained shopping-intent parser. "
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
                        "schema_hint": intent_response_schema(),
                    },
                    sort_keys=True,
                ),
            },
        ],
    }
    if include_json_schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": LLM_INTENT_OUTPUT_SCHEMA_NAME.replace(".", "_"),
                "strict": True,
                "schema": intent_response_schema(),
            },
        }
    return payload


def intent_response_schema() -> dict[str, Any]:
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


def extract_chat_content(response: Mapping[str, Any], *, provider: str) -> Mapping[str, Any]:
    try:
        choices = response["choices"]
        if not isinstance(choices, list) or not choices:
            raise RuntimeError(f"{provider} response missing choices")
        first_choice = choices[0]
        if not isinstance(first_choice, Mapping):
            raise RuntimeError(f"{provider} choice is not an object")
        message = first_choice["message"]
        if not isinstance(message, Mapping):
            raise RuntimeError(f"{provider} message is not an object")
        content = message["content"]
        if not isinstance(content, str):
            raise RuntimeError(f"{provider} content is not a string")
        # Some providers wrap JSON in markdown fences.
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
        parsed = json.loads(cleaned)
    except KeyError as exc:
        raise RuntimeError(f"{provider} response is missing fields") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{provider} content is invalid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise RuntimeError(f"{provider} content is not an object")
    return parsed


def extract_usage(response: Mapping[str, Any]) -> ProviderUsage:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return ProviderUsage()
    prompt = usage.get("prompt_tokens", usage.get("input_tokens", 0))
    completion = usage.get("completion_tokens", usage.get("output_tokens", 0))
    return ProviderUsage(
        prompt_tokens=int(prompt or 0),
        completion_tokens=int(completion or 0),
    )
