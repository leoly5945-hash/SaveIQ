from app.core.settings import Settings


def test_render_postgresql_url_uses_psycopg_driver() -> None:
    settings = Settings(DATABASE_URL="postgresql://user:pass@example.com:5432/app")

    assert settings.database_url == "postgresql+psycopg://user:pass@example.com:5432/app"


def test_legacy_postgres_url_uses_psycopg_driver() -> None:
    settings = Settings(DATABASE_URL="postgres://user:pass@example.com:5432/app")

    assert settings.database_url == "postgresql+psycopg://user:pass@example.com:5432/app"


def test_render_database_url_adds_sslmode() -> None:
    settings = Settings(
        DATABASE_URL=("postgresql://user:pass@dpg-xxx-a.oregon-postgres.render.com/dealhunter")
    )

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "sslmode=require" in settings.database_url


def test_llm_intent_parser_settings_default_to_disabled() -> None:
    settings = Settings(OPENAI_API_KEY="  ")

    assert settings.feature_llm_intent_parser is False
    assert settings.llm_intent_parser_mode == "disabled"
    assert settings.openai_api_key is None
    assert settings.openai_intent_model == "gpt-4.1-mini"
    assert settings.openai_intent_timeout_seconds == 10.0


def test_ai_router_settings_default_to_disabled() -> None:
    settings = Settings()

    assert settings.feature_ai_router is False
    assert settings.ai_router_mode == "disabled"
    assert settings.ai_router_default_model == "intent-parser-v0"
    assert settings.ai_router_strategy == "cost_optimized"
    assert settings.anthropic_api_key is None
    assert settings.ai_router_cache_enabled is True


def test_bandit_router_settings_default_to_disabled() -> None:
    settings = Settings()

    assert settings.feature_bandit_router is False
    assert settings.bandit_router_mode == "disabled"
    assert settings.bandit_epsilon == 0.1
    assert settings.bandit_alpha == 0.5


def test_personalization_settings_default_to_disabled() -> None:
    settings = Settings()

    assert settings.feature_personalization is False
    assert settings.personalization_cache_enabled is True
    assert settings.bandit_reward_delta == 0.0
