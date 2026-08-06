from app.core.settings import Settings


def test_render_postgresql_url_uses_psycopg_driver() -> None:
    settings = Settings(DATABASE_URL="postgresql://user:pass@example.com:5432/app")

    assert settings.database_url == "postgresql+psycopg://user:pass@example.com:5432/app"


def test_legacy_postgres_url_uses_psycopg_driver() -> None:
    settings = Settings(DATABASE_URL="postgres://user:pass@example.com:5432/app")

    assert settings.database_url == "postgresql+psycopg://user:pass@example.com:5432/app"


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
