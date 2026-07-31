from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.settings import Settings
from app.services.llm_intent_contract import LlmIntentParserInput
from app.services.llm_intent_parser import (
    OPENAI_CHAT_COMPLETIONS_URL,
    LlmIntentParserService,
    OpenAIIntentParserClient,
    build_llm_intent_parser_service,
)


class RecordingMockIntentClient:
    def __init__(self, output: Mapping[str, Any]) -> None:
        self.output = output
        self.last_request: LlmIntentParserInput | None = None
        self.last_model: str | None = None
        self.last_timeout: float | None = None

    def parse_intent(
        self,
        request: LlmIntentParserInput,
        *,
        model: str,
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        self.last_request = request
        self.last_model = model
        self.last_timeout = timeout_seconds
        return self.output


class RecordingOpenAITransport:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response
        self.last_url: str | None = None
        self.last_headers: Mapping[str, str] | None = None
        self.last_payload: Mapping[str, Any] | None = None
        self.last_timeout: float | None = None

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        self.last_url = url
        self.last_headers = headers
        self.last_payload = payload
        self.last_timeout = timeout_seconds
        return self.response


def test_llm_intent_parser_falls_back_when_feature_disabled() -> None:
    settings = Settings(FEATURE_LLM_INTENT_PARSER="false", LLM_INTENT_PARSER_MODE="mock")
    service = LlmIntentParserService(settings)

    result = service.parse("fresh earbuds")

    assert result.fallback_required is True
    assert result.fallback_reason == "feature flag disabled"
    assert result.parsed_intent is None


def test_llm_intent_parser_falls_back_without_openai_key() -> None:
    settings = Settings(FEATURE_LLM_INTENT_PARSER="true", LLM_INTENT_PARSER_MODE="openai")
    service = LlmIntentParserService(settings)

    result = service.parse("fresh earbuds")

    assert result.fallback_required is True
    assert result.fallback_reason == "OpenAI API key missing"


def test_llm_intent_parser_uses_mockable_client_and_validates_output() -> None:
    settings = Settings(
        FEATURE_LLM_INTENT_PARSER="true",
        LLM_INTENT_PARSER_MODE="mock",
        OPENAI_INTENT_MODEL="mock-intent-model",
        OPENAI_INTENT_TIMEOUT_SECONDS="2.5",
    )
    client = RecordingMockIntentClient(
        {
            "search_query": "wireless earbuds",
            "has_coupon": True,
            "has_cashback": None,
            "freshness": "fresh",
            "sort": "price_asc",
            "confidence": 0.91,
            "reasoning_summary": "Parsed a shopping intent for fresh coupon earbuds.",
        }
    )
    service = LlmIntentParserService(settings, client)

    result = service.parse("Find fresh wireless earbuds with coupon", market="CA")

    assert result.fallback_required is False
    assert result.parsed_intent is not None
    assert result.parsed_intent.search_query == "wireless earbuds"
    assert client.last_request is not None
    assert client.last_request.raw_intent == "Find fresh wireless earbuds with coupon"
    assert client.last_model == "mock-intent-model"
    assert client.last_timeout == 2.5


def test_llm_intent_parser_falls_back_on_invalid_output() -> None:
    settings = Settings(FEATURE_LLM_INTENT_PARSER="true", LLM_INTENT_PARSER_MODE="mock")
    client = RecordingMockIntentClient(
        {
            "search_query": "wireless earbuds",
            "sort": "merchant_rating",
            "confidence": 0.91,
            "reasoning_summary": "Unsupported sort should fail.",
        }
    )
    service = LlmIntentParserService(settings, client)

    result = service.parse("Find earbuds")

    assert result.fallback_required is True
    assert result.fallback_reason == "LLM parser output invalid: ValidationError"


def test_llm_intent_parser_falls_back_on_low_confidence() -> None:
    settings = Settings(FEATURE_LLM_INTENT_PARSER="true", LLM_INTENT_PARSER_MODE="mock")
    client = RecordingMockIntentClient(
        {
            "search_query": "wireless earbuds",
            "sort": "price_asc",
            "confidence": 0.4,
            "reasoning_summary": "Ambiguous intent.",
        }
    )
    service = LlmIntentParserService(settings, client)

    result = service.parse("maybe something")

    assert result.fallback_required is True
    assert result.fallback_reason == "LLM confidence below 0.60"
    assert result.parsed_intent is not None


def test_openai_intent_parser_client_builds_schema_request_and_extracts_json() -> None:
    transport = RecordingOpenAITransport(
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"search_query":"wireless earbuds","has_coupon":true,'
                            '"has_cashback":null,"freshness":"fresh","sort":"price_asc",'
                            '"confidence":0.93,'
                            '"reasoning_summary":"Parsed coupon earbuds intent."}'
                        )
                    }
                }
            ]
        }
    )
    client = OpenAIIntentParserClient("test-api-key", transport)

    result = client.parse_intent(
        LlmIntentParserInput(raw_intent="Find fresh wireless earbuds with coupon"),
        model="gpt-test-intent",
        timeout_seconds=3.0,
    )

    assert result["search_query"] == "wireless earbuds"
    assert result["has_coupon"] is True
    assert transport.last_url == OPENAI_CHAT_COMPLETIONS_URL
    assert transport.last_headers is not None
    assert transport.last_headers["Authorization"] == "Bearer test-api-key"
    assert transport.last_payload is not None
    assert transport.last_payload["model"] == "gpt-test-intent"
    assert transport.last_payload["response_format"]["type"] == "json_schema"
    schema = transport.last_payload["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert "fallback_reason" in schema["required"]
    assert transport.last_timeout == 3.0


def test_openai_intent_parser_client_errors_are_safe_for_fallback() -> None:
    transport = RecordingOpenAITransport({"choices": [{"message": {"content": "not json"}}]})
    client = OpenAIIntentParserClient("secret-key", transport)

    try:
        client.parse_intent(
            LlmIntentParserInput(raw_intent="Find fresh wireless earbuds"),
            model="gpt-test-intent",
            timeout_seconds=3.0,
        )
    except RuntimeError as exc:
        assert "secret-key" not in str(exc)
        assert str(exc) == "OpenAI intent parser content is invalid JSON"
    else:
        raise AssertionError("expected invalid OpenAI JSON to raise RuntimeError")


def test_build_llm_intent_parser_service_adds_openai_client_when_enabled() -> None:
    settings = Settings(
        FEATURE_LLM_INTENT_PARSER="true",
        LLM_INTENT_PARSER_MODE="openai",
        OPENAI_API_KEY="test-api-key",
    )

    service = build_llm_intent_parser_service(settings)

    assert isinstance(service, LlmIntentParserService)
