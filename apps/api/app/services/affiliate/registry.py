from app.services.affiliate.mock_provider import MockAffiliateProvider
from app.services.affiliate.schemas import AffiliateProviderAdapter


class AffiliateProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, AffiliateProviderAdapter] = {}

    def register(self, provider: AffiliateProviderAdapter) -> None:
        self._providers[provider.source] = provider

    def get(self, source: str) -> AffiliateProviderAdapter:
        return self._providers[source]

    def list(self) -> list[AffiliateProviderAdapter]:
        return list(self._providers.values())


registry = AffiliateProviderRegistry()
registry.register(MockAffiliateProvider())
