from app.services.affiliate.mock_provider import MockAffiliateProvider
from app.services.affiliate.registry import registry
from app.services.affiliate.schemas import (
    AffiliateProviderAdapter,
    NormalizedCashbackOffer,
    NormalizedCoupon,
    NormalizedProductOffer,
    ProviderRawRecord,
)

__all__ = [
    "AffiliateProviderAdapter",
    "MockAffiliateProvider",
    "NormalizedCashbackOffer",
    "NormalizedCoupon",
    "NormalizedProductOffer",
    "ProviderRawRecord",
    "registry",
]
