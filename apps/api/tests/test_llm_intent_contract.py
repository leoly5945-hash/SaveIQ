import pytest
from pydantic import ValidationError

from app.services.llm_intent_contract import (
    LLM_INTENT_CONTRACT_VERSION,
    LLM_INTENT_OUTPUT_SCHEMA_NAME,
    LLM_INTENT_PROMPT_VERSION,
    LlmIntentParserInput,
    LlmParsedIntent,
    build_llm_intent_parser_contract,
)


def test_llm_intent_contract_exposes_versioned_schemas() -> None:
    contract = build_llm_intent_parser_contract()

    assert contract["contract_version"] == LLM_INTENT_CONTRACT_VERSION
    assert contract["prompt_version"] == LLM_INTENT_PROMPT_VERSION
    assert contract["output_schema_name"] == LLM_INTENT_OUTPUT_SCHEMA_NAME
    assert contract["fallback_policy"]["fallback_parser"] == "intent-parser-v0"
    assert "confidence below 0.60" in contract["fallback_policy"]["fallback_when"]
    assert "do not browse the web or call affiliate networks" in contract["guardrails"]
    assert contract["output_schema"]["additionalProperties"] is False


def test_llm_intent_parser_input_normalizes_basic_context() -> None:
    payload = LlmIntentParserInput(raw_intent="  Find fresh earbuds  ", market=" CA ")

    assert payload.raw_intent == "Find fresh earbuds"
    assert payload.market == "CA"
    assert payload.locale == "en-US"
    assert payload.allowed_sorts == ("price_asc", "price_desc", "clicks_desc")


def test_llm_parsed_intent_accepts_expected_output_shape() -> None:
    parsed = LlmParsedIntent(
        search_query=" wireless earbuds ",
        has_coupon=True,
        has_cashback=None,
        freshness="fresh",
        sort="price_asc",
        confidence=0.84,
        reasoning_summary=" User asked for fresh earbuds with coupon preference. ",
    )

    assert parsed.search_query == "wireless earbuds"
    assert parsed.has_coupon is True
    assert parsed.has_cashback is None
    assert parsed.freshness == "fresh"
    assert parsed.sort == "price_asc"
    assert parsed.fallback_reason is None


def test_llm_parsed_intent_rejects_unknown_fields_and_sorts() -> None:
    with pytest.raises(ValidationError):
        LlmParsedIntent(
            search_query="buds",
            sort="merchant_rating",
            confidence=0.8,
            reasoning_summary="Unsupported sort.",
        )

    with pytest.raises(ValidationError):
        LlmParsedIntent(
            search_query="buds",
            sort="price_asc",
            confidence=0.8,
            reasoning_summary="Extra field should fail.",
            merchant="Maple Tech",
        )


def test_llm_parsed_intent_requires_bounded_confidence() -> None:
    with pytest.raises(ValidationError):
        LlmParsedIntent(
            search_query="buds",
            sort="price_asc",
            confidence=1.2,
            reasoning_summary="Confidence must be bounded.",
        )
