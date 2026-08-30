from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AffiliateLink, MerchantListing, Offer
from app.services.affiliate.curated_provider import CURATED_DEALS_PATH, CuratedAmazonProvider
from app.services.affiliate.ingestion import AffiliateIngestionService

EXPECTED_DEAL_COUNT = 20


def test_catalogue_file_is_well_formed() -> None:
    data = json.loads(CURATED_DEALS_PATH.read_text(encoding="utf-8"))
    assert isinstance(data["deals"], list)
    assert len(data["deals"]) == EXPECTED_DEAL_COUNT
    asins = [deal["asin"] for deal in data["deals"]]
    assert len(set(asins)) == len(asins), "ASINs must be unique"
    for deal in data["deals"]:
        assert deal["price_cents"] > 0
        assert deal["asin"].startswith("B")
        assert set(deal) >= {
            "asin",
            "title",
            "brand",
            "category",
            "category_slug",
            "price_cents",
            "price_checked",
            "blurb",
        }


def test_provider_normalizes_with_associate_tag() -> None:
    provider = CuratedAmazonProvider(associate_tag="test-20")
    records = provider._records
    assert len(records) == EXPECTED_DEAL_COUNT

    normalized = provider.normalize_record(records[0])
    assert (
        normalized.affiliate_url
        == f"https://www.amazon.ca/dp/{normalized.provider_product_id}?tag=test-20"
    )
    assert normalized.product_url == f"https://www.amazon.ca/dp/{normalized.provider_product_id}"
    assert normalized.sale_price_cents is None
    assert normalized.currency == "CAD"
    assert normalized.market == "CA"
    assert normalized.provider_metadata["curated"] is True
    assert normalized.provider_metadata["price_checked"] == "2026-08-29"


def test_provider_rejects_incomplete_record() -> None:
    provider = CuratedAmazonProvider(associate_tag="test-20")
    record = provider._records[0].model_copy(deep=True)
    record.payload["title"] = ""
    result = provider.validate_record(record)
    assert result.is_valid is False
    assert result.error_code == "missing_required_field"

    record2 = provider._records[0].model_copy(deep=True)
    record2.payload["price_cents"] = 0
    result2 = provider.validate_record(record2)
    assert result2.is_valid is False
    assert result2.error_code == "invalid_price"


@pytest.mark.asyncio
async def test_curated_sync_ingests_real_offers(db_session: Session) -> None:
    provider = CuratedAmazonProvider(associate_tag="saveiq-20")
    result = await AffiliateIngestionService(db_session, provider).run_sync()

    assert result.stats.received == EXPECTED_DEAL_COUNT
    assert result.stats.rejected == 0
    assert result.stats.errors == 0
    assert db_session.scalar(select(func.count()).select_from(Offer)) == EXPECTED_DEAL_COUNT

    offers = db_session.scalars(select(Offer)).all()
    assert {offer.provider_source for offer in offers} == {"amazon_ca"}

    listings = db_session.scalars(select(MerchantListing)).all()
    assert all((listing.provider_metadata or {}).get("curated") for listing in listings)

    links = db_session.scalars(select(AffiliateLink)).all()
    assert links
    assert all(link.url.startswith("https://www.amazon.ca/dp/") for link in links)
    assert all("tag=saveiq-20" in link.url for link in links)


@pytest.mark.asyncio
async def test_curated_sync_is_idempotent(db_session: Session) -> None:
    first = await AffiliateIngestionService(
        db_session, CuratedAmazonProvider(associate_tag="saveiq-20")
    ).run_sync()
    assert first.stats.inserted > 0

    offers_after_first = db_session.scalar(select(func.count()).select_from(Offer))
    db_session.rollback()

    # Byte-identical re-run: dedup on the raw-record hash, no new offers.
    second = await AffiliateIngestionService(
        db_session, CuratedAmazonProvider(associate_tag="saveiq-20")
    ).run_sync()

    assert db_session.scalar(select(func.count()).select_from(Offer)) == offers_after_first
    assert second.stats.inserted == 0
    assert second.stats.duplicate == EXPECTED_DEAL_COUNT
