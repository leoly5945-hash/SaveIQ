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
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    anthropic_intent_model: str = Field(
        default="claude-3-5-haiku-latest",
        validation_alias="ANTHROPIC_INTENT_MODEL",
    )
    anthropic_intent_timeout_seconds: float = Field(
        default=10.0,
        validation_alias="ANTHROPIC_INTENT_TIMEOUT_SECONDS",
    )
    feature_ai_router: bool = Field(
        default=False,
        validation_alias="FEATURE_AI_ROUTER",
    )
    ai_router_mode: Literal["disabled", "mock", "live"] = Field(
        default="disabled",
        validation_alias="AI_ROUTER_MODE",
    )
    ai_router_default_model: str = Field(
        default="intent-parser-v0",
        validation_alias="AI_ROUTER_DEFAULT_MODEL",
    )
    ai_router_strategy: Literal["cost_optimized", "quality_optimized"] = Field(
        default="cost_optimized",
        validation_alias="AI_ROUTER_STRATEGY",
    )
    ai_router_fallback_provider: Literal[
        "openai",
        "anthropic",
        "mock",
        "deepseek",
        "qwen",
        "ernie",
        "none",
    ] = Field(
        default="openai",
        validation_alias="AI_ROUTER_FALLBACK_PROVIDER",
    )
    ai_router_cache_enabled: bool = Field(
        default=True,
        validation_alias="AI_ROUTER_CACHE_ENABLED",
    )
    ai_router_cache_ttl_seconds: int = Field(
        default=300,
        validation_alias="AI_ROUTER_CACHE_TTL_SECONDS",
    )
    feature_bandit_router: bool = Field(
        default=False,
        validation_alias="FEATURE_BANDIT_ROUTER",
    )
    bandit_router_mode: Literal["disabled", "logging", "active"] = Field(
        default="disabled",
        validation_alias="BANDIT_ROUTER_MODE",
    )
    bandit_epsilon: float = Field(default=0.1, validation_alias="BANDIT_EPSILON")
    bandit_alpha: float = Field(default=0.5, validation_alias="BANDIT_ALPHA")
    bandit_min_samples_ready: int = Field(
        default=10,
        validation_alias="BANDIT_MIN_SAMPLES_READY",
    )
    bandit_reward_alpha: float = Field(default=0.5, validation_alias="BANDIT_REWARD_ALPHA")
    bandit_reward_beta: float = Field(default=0.3, validation_alias="BANDIT_REWARD_BETA")
    bandit_reward_gamma: float = Field(default=0.2, validation_alias="BANDIT_REWARD_GAMMA")
    bandit_reward_delta: float = Field(default=0.0, validation_alias="BANDIT_REWARD_DELTA")
    feature_personalization: bool = Field(
        default=False,
        validation_alias="FEATURE_PERSONALIZATION",
    )
    personalization_cache_enabled: bool = Field(
        default=True,
        validation_alias="PERSONALIZATION_CACHE_ENABLED",
    )
    personalization_cache_ttl_seconds: int = Field(
        default=300,
        validation_alias="PERSONALIZATION_CACHE_TTL_SECONDS",
    )
    # Gate 9 — Chinese providers + advanced optimization (all default off/safe).
    feature_chinese_llm_providers: bool = Field(
        default=False,
        validation_alias="FEATURE_CHINESE_LLM_PROVIDERS",
    )
    deepseek_api_key: str | None = Field(default=None, validation_alias="DEEPSEEK_API_KEY")
    deepseek_intent_model: str = Field(
        default="deepseek-chat",
        validation_alias="DEEPSEEK_INTENT_MODEL",
    )
    deepseek_intent_timeout_seconds: float = Field(
        default=10.0,
        validation_alias="DEEPSEEK_INTENT_TIMEOUT_SECONDS",
    )
    dashscope_api_key: str | None = Field(default=None, validation_alias="DASHSCOPE_API_KEY")
    qwen_intent_model: str = Field(
        default="qwen-plus",
        validation_alias="QWEN_INTENT_MODEL",
    )
    qwen_intent_timeout_seconds: float = Field(
        default=10.0,
        validation_alias="QWEN_INTENT_TIMEOUT_SECONDS",
    )
    baidu_api_key: str | None = Field(default=None, validation_alias="BAIDU_API_KEY")
    baidu_secret_key: str | None = Field(default=None, validation_alias="BAIDU_SECRET_KEY")
    ernie_intent_model: str = Field(
        default="ernie-speed-128k",
        validation_alias="ERNIE_INTENT_MODEL",
    )
    ernie_intent_timeout_seconds: float = Field(
        default=10.0,
        validation_alias="ERNIE_INTENT_TIMEOUT_SECONDS",
    )
    bandit_policy: Literal["rule", "linucb", "neural", "rlhf"] = Field(
        default="linucb",
        validation_alias="BANDIT_POLICY",
    )
    feature_neural_bandit: bool = Field(
        default=False,
        validation_alias="FEATURE_NEURAL_BANDIT",
    )
    feature_rlhf_router: bool = Field(
        default=False,
        validation_alias="FEATURE_RLHF_ROUTER",
    )
    feature_llm_user_embedding: bool = Field(
        default=False,
        validation_alias="FEATURE_LLM_USER_EMBEDDING",
    )
    feature_bayesian_tuning: bool = Field(
        default=False,
        validation_alias="FEATURE_BAYESIAN_TUNING",
    )
    feature_auto_tuning: bool = Field(
        default=False,
        validation_alias="FEATURE_AUTO_TUNING",
    )
    # Gate 10A — rate limits (default off for local/tests; on in production Blueprint).
    rate_limit_enabled: bool = Field(
        default=False,
        validation_alias="RATE_LIMIT_ENABLED",
    )
    rate_limit_public_per_minute: int = Field(
        default=100,
        validation_alias="RATE_LIMIT_PUBLIC_PER_MINUTE",
    )
    rate_limit_auth_per_minute: int = Field(
        default=1000,
        validation_alias="RATE_LIMIT_AUTH_PER_MINUTE",
    )
    rate_limit_admin_per_minute: int = Field(
        default=50,
        validation_alias="RATE_LIMIT_ADMIN_PER_MINUTE",
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

    @field_validator("ai_router_mode")
    @classmethod
    def normalize_ai_router_mode(cls, value: str) -> str:
        return value.lower()

    @field_validator("ai_router_strategy")
    @classmethod
    def normalize_ai_router_strategy(cls, value: str) -> str:
        return value.lower()

    @field_validator("ai_router_fallback_provider")
    @classmethod
    def normalize_ai_router_fallback_provider(cls, value: str) -> str:
        return value.lower()

    @field_validator("bandit_router_mode")
    @classmethod
    def normalize_bandit_router_mode(cls, value: str) -> str:
        return value.lower()

    @field_validator("bandit_policy")
    @classmethod
    def normalize_bandit_policy(cls, value: str) -> str:
        return value.lower()

    @field_validator("ai_router_default_model")
    @classmethod
    def normalize_ai_router_default_model(cls, value: str) -> str:
        stripped = value.strip()
        return stripped or "intent-parser-v0"

    @field_validator(
        "openai_api_key",
        "anthropic_api_key",
        "deepseek_api_key",
        "dashscope_api_key",
        "baidu_api_key",
        "baidu_secret_key",
    )
    @classmethod
    def normalize_optional_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+psycopg://", 1)
        elif value.startswith("postgres://"):
            value = value.replace("postgres://", "postgresql+psycopg://", 1)

        # Render Postgres requires TLS for many connection paths; keep local URLs untouched.
        host_markers = (
            ".render.com",
            "-a.oregon-postgres.render.com",
            ".postgres.database.azure.com",
        )
        if any(marker in value for marker in host_markers) and "sslmode=" not in value:
            separator = "&" if "?" in value else "?"
            value = f"{value}{separator}sslmode=require"
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
