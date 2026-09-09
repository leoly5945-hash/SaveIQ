"""Provider registry + the default registry built from settings (CP4)."""

from __future__ import annotations

import builtins
import logging

from app.core.settings import Settings, get_settings
from app.providers.base import ProductDataProvider, ProviderCapability

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """A name -> :class:`ProductDataProvider` map with capability lookups."""

    def __init__(self) -> None:
        self._providers: dict[str, ProductDataProvider] = {}

    def register(self, provider: ProductDataProvider) -> None:
        if provider.name in self._providers:
            raise ValueError(f"provider {provider.name!r} is already registered")
        self._providers[provider.name] = provider

    def get(self, name: str) -> ProductDataProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise KeyError(f"no product data provider named {name!r}") from exc

    def try_get(self, name: str) -> ProductDataProvider | None:
        return self._providers.get(name)

    def list(self) -> builtins.list[ProductDataProvider]:
        return list(self._providers.values())

    def names(self) -> builtins.list[str]:
        return sorted(self._providers)

    def with_capability(self, capability: ProviderCapability) -> builtins.list[ProductDataProvider]:
        return [p for p in self._providers.values() if capability in p.capabilities]

    def __len__(self) -> int:
        return len(self._providers)

    def __contains__(self, name: object) -> bool:
        return name in self._providers


def build_default_registry(settings: Settings | None = None) -> ProviderRegistry:
    """Register every provider that is configured in ``settings``.

    A provider whose credentials are absent is skipped, not registered in a
    broken state — an empty registry is a valid state (nothing is wired yet).
    """

    settings = settings or get_settings()
    registry = ProviderRegistry()

    if settings.keepa_api_key:
        # Imported lazily so the package has no hard dependency on any one adapter.
        from app.providers.keepa import KeepaProvider

        registry.register(
            KeepaProvider(
                api_key=settings.keepa_api_key,
                domain=settings.keepa_domain,
                timeout_seconds=settings.keepa_timeout_seconds,
            )
        )
        logger.info("provider registered", extra={"provider": "keepa"})
    else:
        logger.info("provider skipped (not configured)", extra={"provider": "keepa"})

    if settings.dataforseo_login and settings.dataforseo_password:
        from app.providers.dataforseo import DataForSEOProvider

        registry.register(
            DataForSEOProvider(
                login=settings.dataforseo_login,
                password=settings.dataforseo_password,
                location_code=settings.dataforseo_location_code,
                language_code=settings.dataforseo_language_code,
                timeout_seconds=settings.dataforseo_timeout_seconds,
            )
        )
        logger.info("provider registered", extra={"provider": "dataforseo"})
    else:
        logger.info("provider skipped (not configured)", extra={"provider": "dataforseo"})

    return registry


_default_registry: ProviderRegistry | None = None


def get_provider_registry() -> ProviderRegistry:
    """Process-wide default registry, built once from ``get_settings()``."""

    global _default_registry
    if _default_registry is None:
        _default_registry = build_default_registry()
    return _default_registry


def reset_provider_registry_for_tests() -> None:
    global _default_registry
    _default_registry = None
