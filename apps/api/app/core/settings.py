from functools import lru_cache

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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.lower()

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
