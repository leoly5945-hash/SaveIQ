from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    public_brand_name: str = Field(default="DealHunter", validation_alias="PUBLIC_BRAND_NAME")
    app_name: str = Field(default="DealHunter API", validation_alias="APP_NAME")
    app_version: str = "0.1.0"
    database_url: str = Field(
        default="postgresql+psycopg://dealhunter:dealhunter@localhost:5432/dealhunter",
        validation_alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    api_cors_origins: str = Field(
        default="http://localhost:3000",
        validation_alias="API_CORS_ORIGINS",
    )
    log_level: str = Field(default="info", validation_alias="LOG_LEVEL")
    admin_api_token: str = Field(default="dev-admin-token", validation_alias="ADMIN_API_TOKEN")
    feature_llm_intent_parser: bool = Field(
        default=False,
        validation_alias="FEATURE_LLM_INTENT_PARSER",
    )
    llm_intent_parser_mode: Literal["disabled", "mock", "openai"] = Field(
        default="disabled",
        validation_alias="LLM_INTENT_PARSER_MODE",
    )
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_intent_model: str = Field(
        default="gpt-4.1-mini",
        validation_alias="OPENAI_INTENT_MODEL",
    )
    openai_intent_timeout_seconds: float = Field(
        default=10.0,
        validation_alias="OPENAI_INTENT_TIMEOUT_SECONDS",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.lower()

    @field_validator("llm_intent_parser_mode")
    @classmethod
    def normalize_llm_intent_parser_mode(cls, value: str) -> str:
        return value.lower()

    @field_validator("openai_api_key")
    @classmethod
    def normalize_openai_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
