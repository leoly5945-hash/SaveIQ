"""DeepSeek intent-parser provider (OpenAI-compatible API)."""

from __future__ import annotations

import time

from app.services.llm_intent_contract import LlmIntentParserInput
from app.services.router.providers.base import ProviderParseResult
from app.services.router.providers.openai_compat import (
    JsonHttpTransport,
    UrllibJsonHttpTransport,
    build_chat_completions_payload,
    extract_chat_content,
    extract_usage,
)

DEEPSEEK_CHAT_COMPLETIONS_URL = "https://api.deepseek.com/chat/completions"


class DeepSeekProvider:
    name = "deepseek"

    def __init__(
        self,
        api_key: str | None,
        transport: JsonHttpTransport | None = None,
        *,
        base_url: str = DEEPSEEK_CHAT_COMPLETIONS_URL,
    ) -> None:
        self._api_key = api_key
        self._transport = transport or UrllibJsonHttpTransport()
        self._base_url = base_url

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
            raise RuntimeError("DeepSeek provider is not configured")
        started = time.perf_counter()
        response = self._transport.post_json(
            self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            payload=build_chat_completions_payload(
                request,
                model=model,
                include_json_schema=False,
            ),
            timeout_seconds=timeout_seconds,
        )
        payload = extract_chat_content(response, provider=self.name)
        return ProviderParseResult(
            provider=self.name,
            model=model,
            payload=dict(payload),
            usage=extract_usage(response),
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
