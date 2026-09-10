"""OpenAI-backed query parse + narration for discovery (gated, fail-safe)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.core.settings import Settings, get_settings
from app.services.discovery.llm import narrate_llm, parse_query_llm
from app.services.discovery.query import parse_shopping_query


def _settings(**over: Any) -> Settings:
    update: dict[str, Any] = dict(
        feature_llm_intent_parser=True,
        llm_intent_parser_mode="openai",
        openai_api_key="sk-test",
        openai_intent_model="gpt-4.1-mini",
        openai_intent_timeout_seconds=5.0,
    )
    update.update(over)
    return get_settings().model_copy(update=update)


class FakeTransport:
    def __init__(self, content: str | None = None, *, raises: bool = False) -> None:
        self._content = content
        self._raises = raises
        self.calls: list[Mapping[str, Any]] = []

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        self.calls.append(payload)
        if self._raises:
            raise RuntimeError("boom")
        return {"choices": [{"message": {"content": self._content}}]}


def _intent_json(**over: Any) -> str:
    base = {
        "search_terms": "power bank",
        "price_min_cents": None,
        "price_max_cents": 10000,
        "confidence": 0.9,
    }
    base.update(over)
    return json.dumps(base)


def test_parse_query_llm_disabled_returns_none() -> None:
    off = _settings(feature_llm_intent_parser=False)
    assert (
        parse_query_llm("power bank under $100", off, transport=FakeTransport(_intent_json()))
        is None
    )


def test_parse_query_llm_happy_path() -> None:
    out = parse_query_llm(
        "a power bank, maybe under a hundred bucks",
        _settings(),
        transport=FakeTransport(_intent_json()),
    )
    assert out is not None
    assert out.search_terms == "power bank"
    assert out.price_max_cents == 10000


def test_parse_query_llm_low_confidence_is_none() -> None:
    fake = FakeTransport(_intent_json(confidence=0.2))
    assert parse_query_llm("something", _settings(), transport=fake) is None


def test_parse_query_llm_bad_json_is_none() -> None:
    assert parse_query_llm("x", _settings(), transport=FakeTransport("not json")) is None


def test_parse_query_llm_transport_error_is_none() -> None:
    assert parse_query_llm("x", _settings(), transport=FakeTransport(raises=True)) is None


def test_parse_shopping_query_uses_llm_when_configured() -> None:
    q = parse_shopping_query(
        "gimme a power bank cheapish",
        settings=_settings(),
        transport=FakeTransport(_intent_json(price_max_cents=8000)),
    )
    assert q.parser_mode == "llm"
    assert q.search_terms == "power bank"
    assert q.price_max_cents == 8000


def test_parse_shopping_query_falls_back_to_rules_on_llm_failure() -> None:
    q = parse_shopping_query(
        "power bank under $100",
        settings=_settings(),
        transport=FakeTransport(raises=True),
    )
    assert q.parser_mode == "rules"
    assert q.search_terms == "power bank"
    assert q.price_max_cents == 10000


def test_parse_shopping_query_no_settings_is_rules() -> None:
    assert parse_shopping_query("power bank under $100").parser_mode == "rules"


def test_narrate_llm_disabled_returns_none() -> None:
    assert narrate_llm(_settings(openai_api_key=None), system="s", user="u") is None


def test_narrate_llm_returns_text() -> None:
    fake = FakeTransport("  Buy it — 13% below average and near the low.  ")
    out = narrate_llm(_settings(), system="s", user="u", transport=fake)
    assert out == "Buy it — 13% below average and near the low."
    assert "response_format" not in fake.calls[0]


def test_narrate_llm_transport_error_is_none() -> None:
    assert (
        narrate_llm(_settings(), system="s", user="u", transport=FakeTransport(raises=True)) is None
    )
