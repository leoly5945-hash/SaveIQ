from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

LLM_INTENT_CONTRACT_VERSION = "llm-intent-contract-2026-07-29-gate-5a"
LLM_INTENT_PROMPT_VERSION = "llm-intent-prompt-v0"
LLM_INTENT_OUTPUT_SCHEMA_NAME = "dealhunter.recommendation_intent.v1"

IntentSort = Literal["price_asc", "price_desc", "clicks_desc"]
IntentFreshness = Literal["fresh"]

LLM_INTENT_ALLOWED_SORTS: tuple[IntentSort, ...] = (
    "price_asc",
    "price_desc",
    "clicks_desc",
)

LLM_INTENT_GUARDRAILS = (
    "parse shopping intent only",
    "return only fields declared in the output schema",
    "do not invent merchants, products, prices, coupons, or cashback",
    "do not browse the web or call affiliate networks",
    "fallback to the rule parser when confidence is low or output is invalid",
)


class LlmIntentParserInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_intent: str = Field(min_length=3, max_length=240)
    market: str = Field(default="CA", min_length=2, max_length=8)
    locale: str = Field(default="en-US", min_length=2, max_length=16)
    allowed_sorts: tuple[IntentSort, ...] = LLM_INTENT_ALLOWED_SORTS

    @field_validator("raw_intent", "market", "locale")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class LlmParsedIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search_query: str | None = Field(default=None, max_length=120)
    has_coupon: bool | None = None
    has_cashback: bool | None = None
    freshness: IntentFreshness | None = None
    sort: IntentSort = "price_asc"
    confidence: float = Field(ge=0, le=1)
    reasoning_summary: str = Field(min_length=1, max_length=240)
    fallback_reason: str | None = Field(default=None, max_length=160)

    @field_validator("search_query", "reasoning_summary", "fallback_reason")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


def build_llm_intent_parser_contract() -> dict[str, Any]:
    return {
        "contract_version": LLM_INTENT_CONTRACT_VERSION,
        "prompt_version": LLM_INTENT_PROMPT_VERSION,
        "output_schema_name": LLM_INTENT_OUTPUT_SCHEMA_NAME,
        "input_schema": LlmIntentParserInput.model_json_schema(),
        "output_schema": LlmParsedIntent.model_json_schema(),
        "allowed_sorts": list(LLM_INTENT_ALLOWED_SORTS),
        "fallback_policy": {
            "fallback_parser": "intent-parser-v0",
            "fallback_when": [
                "feature flag disabled",
                "API key missing",
                "model call fails",
                "model output fails schema validation",
                "confidence below 0.60",
            ],
        },
        "guardrails": list(LLM_INTENT_GUARDRAILS),
    }
