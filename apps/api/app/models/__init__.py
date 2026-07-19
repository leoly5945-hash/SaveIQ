"""SQLAlchemy model modules."""

from app.models.affiliate import (
    AffiliateLink,
    AffiliateProvider,
    AffiliateSyncError,
    AffiliateSyncJob,
    Brand,
    CanonicalProduct,
    CashbackOffer,
    Category,
    Coupon,
    Merchant,
    MerchantListing,
    Offer,
    PriceHistory,
    ProductIdentifier,
    RawProviderRecord,
)

__all__ = [
    "AffiliateLink",
    "AffiliateProvider",
    "AffiliateSyncError",
    "AffiliateSyncJob",
    "Brand",
    "CashbackOffer",
    "CanonicalProduct",
    "Category",
    "Coupon",
    "Merchant",
    "MerchantListing",
    "Offer",
    "PriceHistory",
    "ProductIdentifier",
    "RawProviderRecord",
]
