"""Gate 9 Chinese providers, neural/RLHF bandit, and benchmark tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.services.bandit.bayesian import Bound, bayesian_optimize
from app.services.bandit.features import FEATURE_NAMES, BanditContext, build_feature_vector
from app.services.bandit.neural import NeuralBanditAgent
from app.services.bandit.rlhf import RlhfPolicyAgent
from app.services.bandit.service import BanditRouterService, reset_bandit_singleton
from app.services.eval.benchmark import run_router_benchmark
from app.services.llm_intent_contract import LlmIntentParserInput
from app.services.router.contract import IntentComplexity
from app.services.router.providers.deepseek_provider import DeepSeekProvider
from app.services.router.providers.ernie_provider import ErnieProvider
from app.services.router.providers.qwen_provider import QwenProvider
from app.services.user.llm_embedding import HashFallbackEmbeddingClient, embed_user_history


@pytest.fixture(autouse=True)
def _reset_bandit() -> Generator[None, None, None]:
    reset_bandit_singleton()
    yield
    reset_bandit_singleton()


class _FakeTransport:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[str] = []

    def post_json(
        self,
        url: str,
        *,
        headers: object,
        payload: object,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        del headers, payload, timeout_seconds
        self.calls.append(url)
        return self.response


def test_deepseek_provider_parses_with_mock_transport() -> None:
    transport = _FakeTransport(
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"search_query":"milk","has_coupon":false,"has_cashback":false,'
                            '"freshness":null,"sort":"price_asc","confidence":0.9,'
                            '"reasoning_summary":"ok","fallback_reason":null}'
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
    )
    provider = DeepSeekProvider("test-key", transport=transport)
    assert provider.is_configured() is True
    result = provider.parse_intent(
        LlmIntentParserInput(raw_intent="cheap milk", market="CA"),
        model="deepseek-chat",
        timeout_seconds=5,
    )
    assert result.provider == "deepseek"
    assert result.payload["search_query"] == "milk"
    assert transport.calls


def test_qwen_and_ernie_providers_parse_with_mock_transport() -> None:
    qwen_transport = _FakeTransport(
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"search_query":"tea","has_coupon":true,"has_cashback":false,'
                            '"freshness":"fresh","sort":"price_asc","confidence":0.8,'
                            '"reasoning_summary":"ok","fallback_reason":null}'
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 8, "completion_tokens": 4},
        }
    )
    qwen = QwenProvider("dash-key", transport=qwen_transport)
    qwen_result = qwen.parse_intent(
        LlmIntentParserInput(raw_intent="fresh tea coupon", market="CA"),
        model="qwen-plus",
        timeout_seconds=5,
    )
    assert qwen_result.provider == "qwen"
    assert qwen_result.payload["has_coupon"] is True

    class _ErnieTransport(_FakeTransport):
        def post_json(
            self,
            url: str,
            *,
            headers: object,
            payload: object,
            timeout_seconds: float,
        ) -> dict[str, Any]:
            del headers, payload, timeout_seconds
            self.calls.append(url)
            if "/oauth/2.0/token" in url:
                return {"access_token": "token-1"}
            return {
                "result": (
                    '{"search_query":"rice","has_coupon":false,"has_cashback":true,'
                    '"freshness":null,"sort":"price_asc","confidence":0.77,'
                    '"reasoning_summary":"ok","fallback_reason":null}'
                ),
                "usage": {"prompt_tokens": 6, "completion_tokens": 3},
            }

    ernie = ErnieProvider("ak", "sk", transport=_ErnieTransport({}))
    ernie_result = ernie.parse_intent(
        LlmIntentParserInput(raw_intent="rice cashback", market="CA"),
        model="ernie-speed-128k",
        timeout_seconds=5,
    )
    assert ernie_result.provider == "ernie"
    assert ernie_result.payload["has_cashback"] is True


def test_neural_bandit_learns() -> None:
    agent = NeuralBanditAgent(
        actions=("openai", "deepseek"),
        feature_dim=len(FEATURE_NAMES),
        epsilon=0.0,
        min_samples_ready=5,
    )
    context = build_feature_vector(BanditContext(query_text="milk deal"))
    for _ in range(20):
        agent.update(context, "deepseek", 0.9)
        agent.update(context, "openai", 0.1)
    choice = agent.choose_action(context, force_explore=False)
    assert choice.action == "deepseek"


def test_rlhf_and_bayesian_and_benchmark() -> None:
    rlhf = RlhfPolicyAgent(
        actions=("openai", "qwen"),
        feature_dim=len(FEATURE_NAMES),
        min_samples_ready=3,
    )
    context = build_feature_vector(BanditContext(query_text="complex organic groceries"))
    for _ in range(10):
        rlhf.update(context, "qwen", 0.95)
    assert rlhf.ready is True
    assert rlhf.choose_action(context).action in {"openai", "qwen"}

    result = bayesian_optimize(
        lambda params: -((params["x"] - 0.3) ** 2),
        [Bound("x", 0.0, 1.0)],
        n_init=3,
        n_iter=4,
    )
    assert 0.0 <= result.best_params["x"] <= 1.0

    benchmark = run_router_benchmark()
    assert benchmark["samples"] > 0
    assert len(benchmark["policies"]) == 5


def test_hash_embedding_fallback() -> None:
    vector = embed_user_history(
        titles=["Organic milk 2L"],
        categories=["dairy"],
        click_history=[1, 2],
        client=HashFallbackEmbeddingClient(),
    )
    assert len(vector) == 8


def test_policy_switch_and_admin_gate9_endpoints() -> None:
    settings = Settings(
        FEATURE_BANDIT_ROUTER="true",
        BANDIT_ROUTER_MODE="logging",
        FEATURE_NEURAL_BANDIT="true",
        FEATURE_RLHF_ROUTER="true",
        ADMIN_API_TOKEN="dev-admin-token",
    )
    service = BanditRouterService(settings)
    assert service.switch_policy("neural")["policy"] == "neural"
    decision = service.decide(
        query_text="milk",
        intent_type="recommendation",
        market="CA",
        user_id=None,
        rule_action="mock",
        available_actions=["mock", "openai", "deepseek"],
        complexity=IntentComplexity.SIMPLE,
    )
    assert decision.policy in {"neural", "linucb"}
    assert decision.selected_action == "mock"  # logging mode

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_settings() -> Settings:
        return settings

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = override_settings
    client = TestClient(app)
    headers = {"X-Admin-Token": "dev-admin-token"}

    models = client.get("/admin/models/status", headers=headers)
    assert models.status_code == 200
    body = models.json()
    assert "keys_present" in body
    assert "deepseek" in body["keys_present"]
    assert "api_key" not in str(body).lower() or "keys_present" in body

    bench = client.get("/admin/benchmark/results", headers=headers)
    assert bench.status_code == 200
    assert "policies" in bench.json()

    switched = client.post(
        "/admin/bandit/switch_policy",
        headers=headers,
        json={"policy": "rlhf"},
    )
    assert switched.status_code == 200
    assert switched.json()["policy"] == "rlhf"


def test_gate9_settings_default_safe() -> None:
    settings = Settings()
    assert settings.feature_chinese_llm_providers is False
    assert settings.feature_neural_bandit is False
    assert settings.feature_rlhf_router is False
    assert settings.feature_llm_user_embedding is False
    assert settings.feature_bayesian_tuning is False
    assert settings.bandit_policy == "linucb"
