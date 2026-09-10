"""OpenAI-backed helpers for discovery (Layer 3).

Kept separate from the Gate-6 ``app/services/router`` stack: that one is welded to
the old ``LlmParsedIntent`` schema (coupon / cashback / freshness). Here we want a
shopping-query schema and, later, free-text narration. Same transport shape so
tests can inject canned responses; every failure returns ``None`` so the
deterministic path (rule parser / template) stays the answer.

All calls are gated: ``FEATURE_LLM_INTENT_PARSER`` on, ``LLM_INTENT_PARSER_MODE``
== ``openai``, and ``OPENAI_API_KEY`` set.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.settings import Settings

logger = logging.getLogger(__name__)

_CHAT_URL = "https://api.openai.com/v1/chat/completions"
_MIN_CONFIDENCE = 0.5

_QUERY_SYSTEM = (
    "You turn a shopper's natural-language request into a structured search. "
    "search_terms: the product only, no filler, no price words (keep specs like "
    "'4k' or '1080p'). price_min_cents / price_max_cents: integer cents in the "
    "shopper's currency, or null if not stated ('under $100' -> price_max_cents "
    "10000; '2k' means 2000 dollars). confidence: 0-1, how sure you are."
)

_QUERY_SCHEMA: dict[str, Any] = {
    "name": "shopping_query",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "search_terms": {"type": "string"},
            "price_min_cents": {"type": ["integer", "null"]},
            "price_max_cents": {"type": ["integer", "null"]},
            "confidence": {"type": "number"},
        },
        "required": ["search_terms", "price_min_cents", "price_max_cents", "confidence"],
    },
}


class LlmShoppingIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search_terms: str = Field(min_length=1, max_length=120)
    price_min_cents: int | None = Field(default=None, ge=0)
    price_max_cents: int | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1)


class ChatTransport(Protocol):
    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """POST JSON, return the decoded object."""


class UrllibChatTransport:
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
                body = response.read().decode("utf-8")
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            raise RuntimeError("OpenAI request failed") from exc
        decoded = json.loads(body)
        if not isinstance(decoded, Mapping):
            raise RuntimeError("OpenAI returned a non-object response")
        return decoded


def llm_enabled(settings: Settings) -> bool:
    return bool(
        settings.feature_llm_intent_parser
        and settings.llm_intent_parser_mode == "openai"
        and settings.openai_api_key
    )


def _message_content(response: Mapping[str, Any]) -> str | None:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], Mapping) else None
    content = message.get("content") if isinstance(message, Mapping) else None
    return content if isinstance(content, str) and content.strip() else None


def _chat(
    settings: Settings,
    *,
    messages: list[dict[str, str]],
    response_format: dict[str, Any] | None,
    max_tokens: int,
    transport: ChatTransport | None,
) -> Mapping[str, Any]:
    payload: dict[str, Any] = {
        "model": settings.openai_intent_model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    return (transport or UrllibChatTransport()).post_json(
        _CHAT_URL,
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        payload=payload,
        timeout_seconds=settings.openai_intent_timeout_seconds,
    )


def parse_query_llm(
    raw: str,
    settings: Settings,
    *,
    transport: ChatTransport | None = None,
) -> LlmShoppingIntent | None:
    """LLM shopping-query parse, or ``None`` when disabled / unsure / failed."""

    if not llm_enabled(settings):
        return None
    try:
        response = _chat(
            settings,
            messages=[
                {"role": "system", "content": _QUERY_SYSTEM},
                {"role": "user", "content": raw.strip()[:240]},
            ],
            response_format={"type": "json_schema", "json_schema": _QUERY_SCHEMA},
            max_tokens=200,
            transport=transport,
        )
        content = _message_content(response)
        if content is None:
            return None
        intent = LlmShoppingIntent.model_validate_json(content)
    except (RuntimeError, ValueError, ValidationError):
        logger.warning("llm query parse failed", exc_info=True)
        return None
    if intent.confidence < _MIN_CONFIDENCE:
        return None
    return intent


def narrate_llm(
    settings: Settings,
    *,
    system: str,
    user: str,
    transport: ChatTransport | None = None,
) -> str | None:
    """One short plain-language paragraph, or ``None`` when disabled / failed."""

    if not llm_enabled(settings):
        return None
    try:
        response = _chat(
            settings,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user[:4000]},
            ],
            response_format=None,
            max_tokens=220,
            transport=transport,
        )
        content = _message_content(response)
    except (RuntimeError, ValueError):
        logger.warning("llm narration failed", exc_info=True)
        return None
    return content.strip() if content else None
