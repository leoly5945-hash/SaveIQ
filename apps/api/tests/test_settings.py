from app.core.settings import Settings


def test_render_postgresql_url_uses_psycopg_driver() -> None:
    settings = Settings(DATABASE_URL="postgresql://user:pass@example.com:5432/app")

    assert settings.database_url == "postgresql+psycopg://user:pass@example.com:5432/app"


def test_legacy_postgres_url_uses_psycopg_driver() -> None:
    settings = Settings(DATABASE_URL="postgres://user:pass@example.com:5432/app")

    assert settings.database_url == "postgresql+psycopg://user:pass@example.com:5432/app"
