"""Tests for the CP4 provider registry and the settings-driven default."""

from __future__ import annotations

import pytest

from app.core.settings import Settings
from app.providers.base import ProviderCapability
from app.providers.keepa import KeepaProvider
from app.providers.registry import (
    ProviderRegistry,
    build_default_registry,
    get_provider_registry,
    reset_provider_registry_for_tests,
)


def _keepa() -> KeepaProvider:
    return KeepaProvider(api_key="k", domain=6, transport=_NullTransport())


class _NullTransport:
    def get_json(self, url: str, *, timeout_seconds: float) -> dict[str, object]:
        raise AssertionError("registry tests must not make calls")  # pragma: no cover


def test_register_and_lookup() -> None:
    registry = ProviderRegistry()
    provider = _keepa()
    registry.register(provider)

    assert registry.get("keepa") is provider
    assert registry.try_get("keepa") is provider
    assert registry.try_get("missing") is None
    assert registry.names() == ["keepa"]
    assert "keepa" in registry
    assert len(registry) == 1


def test_register_rejects_duplicate() -> None:
    registry = ProviderRegistry()
    registry.register(_keepa())
    with pytest.raises(ValueError):
        registry.register(_keepa())


def test_get_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        ProviderRegistry().get("nope")


def test_with_capability_filters() -> None:
    registry = ProviderRegistry()
    registry.register(_keepa())
    assert registry.with_capability(ProviderCapability.price_history) == registry.list()
    assert registry.with_capability(ProviderCapability.search) == registry.list()


def test_build_default_registry_skips_keepa_without_key() -> None:
    settings = Settings(KEEPA_API_KEY=None)
    registry = build_default_registry(settings)
    assert len(registry) == 0
    assert "keepa" not in registry


def test_build_default_registry_registers_configured_keepa() -> None:
    settings = Settings(KEEPA_API_KEY="live-key", KEEPA_DOMAIN=6)
    registry = build_default_registry(settings)
    assert "keepa" in registry
    provider = registry.get("keepa")
    assert provider.market == "CA"
    assert provider.currency == "CAD"
    assert provider.is_configured() is True


def test_get_provider_registry_is_cached_and_resettable() -> None:
    reset_provider_registry_for_tests()
    first = get_provider_registry()
    assert get_provider_registry() is first
    reset_provider_registry_for_tests()
    assert get_provider_registry() is not first
