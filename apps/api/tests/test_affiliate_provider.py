import pytest

from app.services.affiliate.mock_provider import MockAffiliateProvider
from app.services.affiliate.schemas import ProviderRecordType


@pytest.mark.asyncio
async def test_mock_provider_contract() -> None:
    provider = MockAffiliateProvider()

    connection = await provider.test_connection()
    merchants = await provider.fetch_merchants()
    records = await provider.fetch_incremental_updates()

    assert connection.ok
    assert len(merchants) >= 3
    product_records = [
        record for record in records if record.record_type == ProviderRecordType.product_offer
    ]
    assert len(product_records) >= 5


@pytest.mark.asyncio
async def test_mock_provider_validation_identifies_malformed_record() -> None:
    provider = MockAffiliateProvider()
    records = await provider.fetch_incremental_updates()
    malformed = next(record for record in records if record.source_record_id == "malformed-record")

    result = provider.validate_record(malformed)

    assert not result.is_valid
    assert result.error_code == "malformed_record"
