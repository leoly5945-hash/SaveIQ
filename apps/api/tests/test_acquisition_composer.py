"""Composing acquisition options from the category/channel rulesets."""

from __future__ import annotations

import pytest

from app.services.acquisition.catalog import load_demo_products, reset_caches_for_tests
from app.services.acquisition.composer import ProductContext, compose_options
from app.services.acquisition.models import AcquisitionKind


@pytest.fixture(autouse=True)
def _fresh_caches() -> None:
    reset_caches_for_tests()


def _kinds(ctx: ProductContext) -> list[AcquisitionKind]:
    return [o.kind for o in compose_options(ctx)]


def test_flagship_phone_gets_the_full_set() -> None:
    ctx = ProductContext(retail_price_cents=159900, category="smartphone", brand="apple")
    opts = compose_options(ctx)
    labels = {o.label for o in opts}
    kinds = {o.kind for o in opts}
    assert AcquisitionKind.retail in kinds
    assert AcquisitionKind.financing in kinds  # carrier financing
    assert AcquisitionKind.lease in kinds  # bring-it-back
    assert AcquisitionKind.refurb in kinds  # apple refurb + amazon renewed
    assert any("Apple Certified Refurbished" in x for x in labels)


def test_non_carrier_item_has_no_carrier_programs() -> None:
    ctx = ProductContext(retail_price_cents=49900, category="headphones", brand="sony")
    kinds = _kinds(ctx)
    # only retail + amazon renewed apply to headphones
    assert AcquisitionKind.financing not in kinds
    assert AcquisitionKind.lease not in kinds
    assert AcquisitionKind.retail in kinds
    assert AcquisitionKind.refurb in kinds


def test_tv_over_threshold_gets_best_buy_financing() -> None:
    ctx = ProductContext(retail_price_cents=259900, category="television", brand="lg")
    labels = {o.label for o in compose_options(ctx)}
    assert any("Best Buy" in x for x in labels)


def test_cheap_item_under_the_retailer_financing_floor_is_excluded() -> None:
    ctx = ProductContext(retail_price_cents=40000, category="television", brand="tcl")
    labels = {o.label for o in compose_options(ctx)}
    assert not any("Best Buy" in x for x in labels)


def test_brand_gate_blocks_apple_refurb_for_a_samsung_phone() -> None:
    ctx = ProductContext(retail_price_cents=150000, category="smartphone", brand="samsung")
    labels = {o.label for o in compose_options(ctx)}
    assert not any("Apple Certified" in x for x in labels)
    assert any("Amazon Renewed" in x for x in labels)  # brand-agnostic refurb still applies


def test_carrier_eligible_false_overrides_a_phone_category() -> None:
    ctx = ProductContext(
        retail_price_cents=150000, category="smartphone", brand="apple", carrier_eligible=False
    )
    kinds = _kinds(ctx)
    assert AcquisitionKind.financing not in kinds
    assert AcquisitionKind.lease not in kinds


def test_lease_residual_is_clamped_and_monthly_backs_it_out() -> None:
    ctx = ProductContext(retail_price_cents=300000, category="smartphone", brand="apple")
    lease = next(o for o in compose_options(ctx) if o.kind == AcquisitionKind.lease)
    assert lease.residual_cents == 55000  # residual_max_cents from programs.json
    # 24 monthly payments of (retail - residual)/24, rounded up
    assert lease.device_monthly_cents == -(-(300000 - 55000) // 24)
    assert lease.returns_at_term is True


def test_resale_comes_from_the_depreciation_curve() -> None:
    ctx = ProductContext(retail_price_cents=100000, category="smartphone", brand="apple")
    retail_opt = next(
        o for o in compose_options(ctx, horizon_months=36) if o.kind == AcquisitionKind.retail
    )
    # smartphone_flagship @ 36 mo = 0.40 in depreciation.json
    assert retail_opt.resale_value_cents == 40000


def test_unknown_category_still_yields_at_least_buy_outright() -> None:
    ctx = ProductContext(retail_price_cents=25000, category="garden_tool", brand="ryobi")
    opts = compose_options(ctx)
    assert opts
    assert AcquisitionKind.retail in {o.kind for o in opts}


def test_zero_price_raises() -> None:
    with pytest.raises(ValueError, match="positive"):
        compose_options(ProductContext(retail_price_cents=0, category="smartphone"))


def test_every_demo_product_composes_and_ranks() -> None:
    from app.services.acquisition import BuyerProfile, compare_paths

    for product in load_demo_products().products:
        ctx = ProductContext(
            retail_price_cents=product.retail_price_cents,
            category=product.category,
            brand=product.brand,
            carrier_eligible=product.carrier_eligible,
        )
        opts = compose_options(ctx)
        assert opts, product.slug
        rec = compare_paths(opts, BuyerProfile(horizon_months=36), product_slug=product.slug)
        assert rec.best_label
        assert all(any("estimate" in n.lower() for n in t.assumptions) for t in rec.ranked)
