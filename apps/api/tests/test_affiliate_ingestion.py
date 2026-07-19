import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AffiliateSyncJob,
    Brand,
    CanonicalProduct,
    CashbackOffer,
    Coupon,
    Merchant,
    MerchantListing,
    Offer,
    PriceHistory,
    ProductIdentifier,
    RawProviderRecord,
)
from app.services.affiliate.ingestion import AffiliateIngestionService, CriticalSyncFailure
from app.services.affiliate.mock_provider import MockAffiliateProvider


async def run_sync(session: Session):
    return await AffiliateIngestionService(session, MockAffiliateProvider()).run_sync()


@pytest.mark.asyncio
async def test_successful_sync_ingests_mock_data(db_session: Session) -> None:
    result = await run_sync(db_session)

    assert result.stats.received == 12
    assert result.stats.rejected == 1
    assert result.stats.duplicate == 1
    assert result.stats.stale == 1
    assert db_session.scalar(select(func.count()).select_from(Merchant)) == 3
    assert db_session.scalar(select(func.count()).select_from(CanonicalProduct)) == 5
    assert db_session.scalar(select(func.count()).select_from(MerchantListing)) == 6
    assert db_session.scalar(select(func.count()).select_from(Offer)) == 6


@pytest.mark.asyncio
async def test_repeated_sync_is_idempotent(db_session: Session) -> None:
    await run_sync(db_session)
    products_after_first = db_session.scalar(select(func.count()).select_from(CanonicalProduct))
    prices_after_first = db_session.scalar(select(func.count()).select_from(PriceHistory))
    db_session.rollback()

    result = await run_sync(db_session)

    assert result.stats.duplicate == 12
    assert (
        db_session.scalar(select(func.count()).select_from(CanonicalProduct))
        == products_after_first
    )
    assert db_session.scalar(select(func.count()).select_from(PriceHistory)) == prices_after_first


@pytest.mark.asyncio
async def test_duplicate_malformed_and_stale_records_are_audited(db_session: Session) -> None:
    await run_sync(db_session)

    raw_statuses = db_session.scalars(select(RawProviderRecord.status)).all()
    error = db_session.scalar(select(func.count()).select_from(AffiliateSyncJob))

    assert "duplicate" in raw_statuses
    assert "rejected" in raw_statuses
    assert "stale" in raw_statuses
    assert error == 1


@pytest.mark.asyncio
async def test_product_matching_by_global_identifier_and_brand_mpn(db_session: Session) -> None:
    await run_sync(db_session)

    wavebuds = db_session.scalars(
        select(MerchantListing).where(
            MerchantListing.provider_product_id.in_(["MT-WAVEBUDS-BLACK", "NO-AWB-2026"])
        )
    ).all()
    pack_product = db_session.scalar(
        select(CanonicalProduct)
        .join(Brand)
        .where(Brand.name == "Boreal Gear", CanonicalProduct.mpn == "BTP-32")
    )

    assert len({listing.canonical_product_id for listing in wavebuds}) == 1
    assert pack_product is not None
    assert db_session.scalar(
        select(ProductIdentifier).where(
            ProductIdentifier.canonical_product_id == pack_product.id,
            ProductIdentifier.identifier_type == "mpn",
            ProductIdentifier.identifier_value == "BTP-32",
        )
    )


@pytest.mark.asyncio
async def test_price_history_appends_only_new_observations(db_session: Session) -> None:
    await run_sync(db_session)
    first_count = db_session.scalar(select(func.count()).select_from(PriceHistory))
    db_session.rollback()

    await run_sync(db_session)

    assert first_count == 6
    assert db_session.scalar(select(func.count()).select_from(PriceHistory)) == first_count


@pytest.mark.asyncio
async def test_coupon_expiry_and_cashback_normalization(db_session: Session) -> None:
    await run_sync(db_session)

    expired_coupon = db_session.scalar(select(Coupon).where(Coupon.code == "SPRING5"))
    cashback = db_session.scalar(select(CashbackOffer).where(CashbackOffer.rate_value_bps == 250))

    assert expired_coupon is not None
    assert expired_coupon.is_expired
    assert cashback is not None
    assert cashback.rate_type == "percent_bps"


@pytest.mark.asyncio
async def test_critical_failure_rolls_back_transaction(db_session: Session) -> None:
    service = AffiliateIngestionService(db_session, MockAffiliateProvider())

    with pytest.raises(CriticalSyncFailure):
        await service.run_sync(simulate_critical_failure=True)

    assert db_session.scalar(select(func.count()).select_from(RawProviderRecord)) == 0
    assert db_session.scalar(select(func.count()).select_from(AffiliateSyncJob)) == 0
