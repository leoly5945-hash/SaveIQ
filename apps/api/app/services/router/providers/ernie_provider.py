"""ERNIE (Baidu Qianfan) intent-parser provider."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

from app.services.llm_intent_contract import (
    LLM_INTENT_GUARDRAILS,
    LLM_INTENT_PROMPT_VERSION,
    LlmIntentParserInput,
)
from app.services.router.providers.base import ProviderParseResult, ProviderUsage
from app.services.router.providers.openai_compat import (
    JsonHttpTransport,
    UrllibJsonHttpTransport,
    extract_chat_content,
    intent_response_schema,
)

BAIDU_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
ERNIE_CHAT_URL_TEMPLATE = (
    "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/{model}"
)


class ErnieProvider:
    """Baidu ERNIE provider using API key + secret key for access tokens."""

    name = "ernie"

    def __init__(
        self,
        api_key: str | None,
        secret_key: str | None,
        transport: JsonHttpTransport | None = None,
        *,
        token_url: str = BAIDU_TOKEN_URL,
        chat_url_template: str = ERNIE_CHAT_URL_TEMPLATE,
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._transport = transport or UrllibJsonHttpTransport()
        self._token_url = token_url
        self._chat_url_template = chat_url_template
        self._cached_token: str | None = None

    def is_configured(self) -> bool:
        return bool(self._api_key and self._secret_key)

    def parse_intent(
        self,
        request: LlmIntentParserInput,
        *,
        model: str,
        timeout_seconds: float,
    ) -> ProviderParseResult:
        if not self.is_configured():
            raise RuntimeError("ERNIE provider is not configured")
        started = time.perf_counter()
        token = self._access_token(timeout_seconds=timeout_seconds)
        url = f"{self._chat_url_template.format(model=model)}?access_token={token}"
        response = self._transport.post_json(
            url,
            headers={"Content-Type": "application/json"},
            payload=_build_ernie_payload(request),
            timeout_seconds=timeout_seconds,
        )
        payload = _extract_ernie_content(response)
        usage = _extract_ernie_usage(response)
        return ProviderParseResult(
            provider=self.name,
            model=model,
            payload=dict(payload),
            usage=usage,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )

    def _access_token(self, *, timeout_seconds: float) -> str:
        if self._cached_token:
            return self._cached_token
        # Token endpoint expects form query params; reuse JSON transport with empty body
        # by posting to a URL that already includes grant params.
        query = urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self._api_key or "",
                "client_secret": self._secret_key or "",
            }
        )
        response = self._transport.post_json(
            f"{self._token_url}?{query}",
            headers={"Content-Type": "application/json"},
            payload={},
            timeout_seconds=timeout_seconds,
        )
        token = response.get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise RuntimeError("ERNIE access token missing")
        self._cached_token = token.strip()
        return self._cached_token


def _build_ernie_payload(request: LlmIntentParserInput) -> dict[str, Any]:
    user_content = json.dumps(
        {
            "prompt_version": LLM_INTENT_PROMPT_VERSION,
            "raw_intent": request.raw_intent,
            "market": request.market,
            "guardrails": list(LLM_INTENT_GUARDRAILS),
            "schema_hint": intent_response_schema(),
            "instruction": "Return only a JSON object matching schema_hint.",
        },
        sort_keys=True,
    )
    return {
        "messages": [{"role": "user", "content": user_content}],
        "temperature": 0.1,
    }


def _extract_ernie_content(response: Mapping[str, Any]) -> Mapping[str, Any]:
    # Qianfan returns {"result": "...json..."} or OpenAI-like choices.
    if "choices" in response:
        return extract_chat_content(response, provider="ernie")
    result = response.get("result")
    if not isinstance(result, str):
        raise RuntimeError("ERNIE response missing result")
    cleaned = result.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ERNIE content is invalid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise RuntimeError("ERNIE content is not an object")
    return parsed


def _extract_ernie_usage(response: Mapping[str, Any]) -> ProviderUsage:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return ProviderUsage()
    prompt = usage.get("prompt_tokens", usage.get("input_tokens", 0))
    completion = usage.get("completion_tokens", usage.get("output_tokens", 0))
    return ProviderUsage(
        prompt_tokens=int(prompt or 0),
        completion_tokens=int(completion or 0),
    )
