"""Tests for CP7 cross-merchant product matching."""

from __future__ import annotations

from datetime import UTC, datetime

from app.providers.base import ProviderOffer
from app.services.decision.matching import (
    build_comparison,
    score_candidate,
    store_page_colour_note,
    store_page_conflict,
    store_page_words,
)

NOW = datetime(2026, 9, 9, tzinfo=UTC)
REF_TITLE = "Anker SOLIX S2000 Portable Power Station, 2010Wh, 1500W Solar Generator"
REF_BRAND = "Anker"
REF_CENTS = 94900  # $949


def _offer(merchant: str, cents: int, title: str, url: str = "https://x") -> ProviderOffer:
    return ProviderOffer(
        provider="dataforseo",
        provider_product_id=REF_TITLE,
        merchant=merchant,
        price_cents=cents,
        currency="CAD",
        url=url,
        observed_at=NOW,
        metadata={"title": title},
    )


# --- score_candidate ----------------------------------------------------


def test_scores_a_clear_match_high() -> None:
    s = score_candidate(
        reference_title=REF_TITLE,
        reference_brand=REF_BRAND,
        reference_price_cents=REF_CENTS,
        candidate_title="Anker SOLIX S2000 Power Station 2010Wh Solar Generator",
        candidate_price_cents=89900,
    )
    assert s >= 0.7


def test_rejects_wrong_brand() -> None:
    assert (
        score_candidate(
            reference_title=REF_TITLE,
            reference_brand=REF_BRAND,
            reference_price_cents=REF_CENTS,
            candidate_title="Jackery Explorer 2000 Portable Power Station Solar Generator",
            candidate_price_cents=95000,
        )
        == 0.0
    )


def test_rejects_accessory() -> None:
    assert (
        score_candidate(
            reference_title=REF_TITLE,
            reference_brand=REF_BRAND,
            reference_price_cents=REF_CENTS,
            candidate_title="Carrying Case for Anker SOLIX S2000 Power Station",
            candidate_price_cents=6900,
        )
        == 0.0
    )


def test_rejects_price_far_out_of_band() -> None:
    assert (
        score_candidate(
            reference_title=REF_TITLE,
            reference_brand=REF_BRAND,
            reference_price_cents=REF_CENTS,
            candidate_title="Anker SOLIX S2000 Power Station bundle with extra battery",
            candidate_price_cents=250000,
        )
        == 0.0
    )


# --- build_comparison -------------------------------------------------


def test_build_comparison_ranks_and_flags_cheaper() -> None:
    candidates = [
        _offer("Best Buy Canada", 91900, "Anker SOLIX S2000 Portable Power Station 2010Wh"),
        _offer("Walmart Canada", 89900, "Anker SOLIX S2000 Power Station 2010Wh Solar"),
        _offer("Some Random Store", 4999, "Phone case compatible with Anker"),  # accessory
        _offer("Jackery Store", 92000, "Jackery Explorer 2000 Solar Generator"),  # wrong product
        _offer("Amazon.ca", 94900, "Anker SOLIX S2000 Portable Power Station"),  # self — skipped
    ]
    comp = build_comparison(
        reference_merchant="Amazon.ca",
        reference_title=REF_TITLE,
        reference_brand=REF_BRAND,
        reference_price_cents=REF_CENTS,
        currency="CAD",
        candidates=candidates,
    )
    assert [o.merchant for o in comp.offers] == ["Walmart Canada", "Best Buy Canada"]
    assert comp.offers[0].price_cents == 89900
    assert comp.cheapest is not None and comp.cheapest.merchant == "Walmart Canada"


def test_build_comparison_drops_offers_above_reference() -> None:
    # only cheaper offers help the shopper — a pricier "same product" is noise.
    candidates = [
        _offer("Best Buy Canada", 99900, "Anker SOLIX S2000 Portable Power Station 2010Wh"),
        _offer("delldxb.com", 225060, "Anker SOLIX S2000 Power Station 2010Wh Solar"),
        _offer("Walmart Canada", 88000, "Anker SOLIX S2000 Power Station 2010Wh Solar"),
    ]
    comp = build_comparison(
        reference_merchant="Amazon.ca",
        reference_title=REF_TITLE,
        reference_brand=REF_BRAND,
        reference_price_cents=REF_CENTS,
        currency="CAD",
        candidates=candidates,
    )
    assert [o.merchant for o in comp.offers] == ["Walmart Canada"]


def test_build_comparison_no_cheaper_when_amazon_wins() -> None:
    candidates = [
        _offer("Best Buy Canada", 99900, "Anker SOLIX S2000 Portable Power Station 2010Wh"),
    ]
    comp = build_comparison(
        reference_merchant="Amazon.ca",
        reference_title=REF_TITLE,
        reference_brand=REF_BRAND,
        reference_price_cents=REF_CENTS,
        currency="CAD",
        candidates=candidates,
    )
    assert comp.offers == []  # nothing cheaper to show
    assert comp.cheapest is None


def test_build_comparison_skips_amazon_family_echo() -> None:
    candidates = [
        _offer("Amazon", 88000, "Anker SOLIX S2000 Portable Power Station 2010Wh"),
        _offer("Amazon.com", 87000, "Anker SOLIX S2000 Portable Power Station"),
        _offer("Amazon Warehouse", 86000, "Anker SOLIX S2000 Power Station 2010Wh Solar"),
        # below the reference (shown) but not past the cheaper margin (not flagged)
        _offer("Best Buy Canada", 94000, "Anker SOLIX S2000 Portable Power Station 2010Wh"),
    ]
    comp = build_comparison(
        reference_merchant="Amazon.ca",
        reference_title=REF_TITLE,
        reference_brand=REF_BRAND,
        reference_price_cents=REF_CENTS,
        currency="CAD",
        candidates=candidates,
    )
    assert [o.merchant for o in comp.offers] == ["Best Buy Canada"]
    assert comp.cheapest is None


def test_build_comparison_lists_weak_match_but_does_not_flag_cheaper() -> None:
    # cheaper price, but a sparse title -> above the inclusion bar, below the
    # "cheaper at X" bar: shown in the list, not flagged.
    candidates = [_offer("Staples Canada", 80000, "Anker SOLIX portable")]
    comp = build_comparison(
        reference_merchant="Amazon.ca",
        reference_title=REF_TITLE,
        reference_brand=REF_BRAND,
        reference_price_cents=REF_CENTS,
        currency="CAD",
        candidates=candidates,
    )
    assert len(comp.offers) == 1
    assert 0.55 <= comp.offers[0].match_confidence < 0.65
    assert comp.cheapest is None


def test_build_comparison_dedupes_merchant_keeps_cheapest() -> None:
    candidates = [
        _offer("Walmart Canada", 91900, "Anker SOLIX S2000 Power Station 2010Wh"),
        _offer("Walmart Canada", 88900, "Anker SOLIX S2000 Power Station 2010Wh Solar"),
    ]
    comp = build_comparison(
        reference_merchant="Amazon.ca",
        reference_title=REF_TITLE,
        reference_brand=REF_BRAND,
        reference_price_cents=REF_CENTS,
        currency="CAD",
        candidates=candidates,
    )
    assert len(comp.offers) == 1
    assert comp.offers[0].price_cents == 88900


def test_rejects_a_different_model_number() -> None:
    # Prod: the BE600M1 check matched Vuugo's cheaper BE425M (a smaller UPS).
    assert (
        score_candidate(
            reference_title=(
                "APC UPS Battery Backup & Surge Protector with USB Charger, "
                "600VA APC Back-UPS (BE600M1)"
            ),
            reference_brand="APC",
            reference_price_cents=11490,
            candidate_title=(
                "APC Back-UPS 425VA / 255W 6 Outlets Battery Backup & Surge "
                "Protector - AC 120V - 6x NEMA 5-15R (BE425M)"
            ),
            candidate_price_cents=9601,
        )
        == 0.0
    )


def test_rejects_a_different_capacity_without_model_numbers() -> None:
    assert (
        score_candidate(
            reference_title="Samsung Galaxy S26 5G 256GB Unlocked Black",
            reference_brand="Samsung",
            reference_price_cents=87299,
            candidate_title="Samsung Galaxy S26 5G 128GB Unlocked Black",
            candidate_price_cents=79999,
        )
        == 0.0
    )


def test_same_model_number_still_matches() -> None:
    s = score_candidate(
        reference_title="APC UPS Battery Backup & Surge Protector 600VA APC Back-UPS (BE600M1)",
        reference_brand="APC",
        reference_price_cents=11490,
        candidate_title="APC Back-UPS 600VA BE600M1 Battery Backup Surge Protector",
        candidate_price_cents=10999,
    )
    assert s >= 0.65


def test_candidate_without_a_model_number_is_not_rejected_for_it() -> None:
    s = score_candidate(
        reference_title="APC UPS Battery Backup 600VA APC Back-UPS (BE600M1)",
        reference_brand="APC",
        reference_price_cents=11490,
        candidate_title="APC Back-UPS 600VA Battery Backup",
        candidate_price_cents=10999,
    )
    assert s > 0.0


def _score(reference: str, candidate: str, ref_cents: int, cand_cents: int, brand: str) -> float:
    return score_candidate(
        reference_title=reference,
        reference_brand=brand,
        reference_price_cents=ref_cents,
        candidate_title=candidate,
        candidate_price_cents=cand_cents,
    )


def test_rejects_a_single_item_against_a_multi_pack() -> None:
    ref = "Crest 3D White Advanced Teeth Whitening Toothpaste, Radiant Mint, 70 Ml (Pack of 4)"
    single = "Crest 3D White Advanced Whitening Toothpaste Radiant Mint 70 mL"
    assert _score(ref, single, 1299, 599, "Crest") == 0.0
    same = "Crest 3D White Advanced Teeth Whitening Toothpaste Radiant Mint 70 mL, 4 Pack"
    assert _score(ref, same, 1299, 1199, "Crest") > 0.55


def test_rejects_a_different_pack_count() -> None:
    ref = "Energizer AA Batteries, Max Double A Battery Alkaline, 20 Count"
    assert _score(ref, "Energizer MAX AA Alkaline Batteries, 8 Pack", 1999, 982, "Energizer") == 0.0
    assert _score(ref, "Energizer MAX AA Alkaline Batteries 20-Pack", 1999, 1799, "Energizer") > 0.0


def test_rejects_a_multi_pack_against_a_single_item() -> None:
    ref = "Logitech M185 Wireless Mouse Grey"
    assert _score(ref, "Logitech M185 Wireless Mouse Grey (2 Pack)", 2399, 2299, "Logitech") == 0.0


def test_rejects_a_different_weight_even_when_written_with_a_space() -> None:
    ref = "CeraVe Moisturizing Cream for Dry-Very Dry Skin on the Face & Body, 539g"
    small = "CeraVe Moisturizing Cream for Dry to Very Dry Skin Face & Body 250 g"
    assert _score(ref, small, 2797, 1500, "CeraVe") == 0.0
    assert _score(ref, small.replace("250 g", "539 g"), 2797, 2500, "CeraVe") > 0.55


def test_rejects_a_much_cheaper_candidate_that_does_not_confirm_the_size() -> None:
    ref = "CeraVe Moisturizing Cream for Dry-Very Dry Skin on the Face & Body, 539g"
    no_size = "CeraVe Moisturizing Cream for Dry to Very Dry Skin Face & Body"
    assert _score(ref, no_size, 2797, 1300, "CeraVe") == 0.0
    other_unit = no_size + " 8 oz"
    assert _score(ref, other_unit, 2797, 1300, "CeraVe") == 0.0
    # Close in price: an unstated size is tolerated.
    assert _score(ref, no_size, 2797, 2229, "CeraVe") > 0.55


def _dyson(merchant: str, cents: int, title: str) -> ProviderOffer:
    return _offer(merchant, cents, title)


def test_weak_match_far_below_the_90_day_low_is_dropped_and_cheapest_is_confident() -> None:
    ref = "Dyson V8 Plus Cordless Vacuum"
    comp = build_comparison(
        reference_merchant="Amazon.ca",
        reference_title=ref,
        reference_brand="Dyson",
        reference_price_cents=59999,
        currency="CAD",
        low_90d_cents=44999,
        candidates=[
            _dyson("Walmart.ca", 27999, "Dyson V8 Stick Vac"),
            _dyson("Best Buy", 44000, "Dyson V8 Stick Vac"),
            _dyson("Dyson Canada", 54999, "Dyson V8 Plus Cordless Vacuum"),
        ],
    )
    merchants = [o.merchant for o in comp.offers]
    assert "Walmart.ca" not in merchants  # weak match, 38% under the 90-day low
    assert "Best Buy" in merchants  # weak match but a believable price: still listed
    # The weak Best Buy row sorts first, yet the confident match is the one named.
    assert comp.cheapest is not None and comp.cheapest.merchant == "Dyson Canada"


def test_only_a_barcode_match_may_sit_far_under_the_90_day_low() -> None:
    ref = "Dyson V15 Detect Plus Cordless Vacuum"

    def build(candidates: list[ProviderOffer]):
        return build_comparison(
            reference_merchant="Amazon.ca",
            reference_title=ref,
            reference_brand="Dyson",
            reference_price_cents=99999,
            currency="CAD",
            low_90d_cents=79999,
            candidates=candidates,
        )

    # Same words, $499 against a $799.99 low: a refurb the title doesn't admit to.
    title_only = _offer("Mobile Vacuum", 49900, "Dyson V15 Detect Plus Cordless Vacuum")
    assert build([title_only]).offers == []

    by_barcode = title_only.model_copy(
        update={"metadata": {**title_only.metadata, "matched_by": "gtin"}}
    )
    assert [o.merchant for o in build([by_barcode]).offers] == ["Mobile Vacuum"]


def test_resale_marketplaces_are_not_store_prices() -> None:
    comp = build_comparison(
        reference_merchant="Amazon.ca",
        reference_title="Dyson V15 Detect Plus Cordless Vacuum",
        reference_brand="Dyson",
        reference_price_cents=99999,
        currency="CAD",
        candidates=[
            _offer("Poshmark Canada", 90000, "Dyson V15 Detect Plus Cordless Vacuum"),
            _offer("Dyson Canada", 94999, "Dyson V15 Detect Plus Cordless Vacuum"),
        ],
    )
    assert [o.merchant for o in comp.offers] == ["Dyson Canada"]


def _ebay(cents: int, title: str = "Sony MDRZX110 Over-Ear Headphones Black") -> ProviderOffer:
    return ProviderOffer(
        provider="ebay",
        provider_product_id="B00NJ2M33I",
        merchant="eBay",
        price_cents=cents,
        currency="CAD",
        url="https://www.ebay.ca/itm/1?campid=5339209072",
        observed_at=datetime(2026, 10, 1, tzinfo=UTC),
        metadata={
            "title": title,
            "matched_by": "gtin",
            "seller_feedback_pct": 99.6,
            "seller_feedback_score": 1200,
        },
    )


def _sony(candidates: list[ProviderOffer]):
    return build_comparison(
        reference_merchant="Amazon.ca",
        reference_title="Sony MDRZX110 Over-Ear Headphones (Black)",
        reference_brand="Sony",
        reference_price_cents=2498,
        currency="CAD",
        candidates=candidates,
    )


def test_ebay_not_cheaper_is_offered_as_also_available_never_as_cheaper() -> None:
    comp = _sony([_ebay(2699), _ebay(2799)])
    assert comp.offers == [] and comp.cheapest is None
    assert comp.also_on_ebay is not None
    assert comp.also_on_ebay.price_cents == 2699  # the lower of the two
    assert comp.also_on_ebay.detail.startswith("New · ships from Canada")

    # Far above Amazon: not worth a line.
    assert _sony([_ebay(3500)]).also_on_ebay is None
    # Another store above Amazon is still dropped; this is an eBay-only allowance.
    walmart = _offer("Walmart.ca", 2699, "Sony MDRZX110 Over-Ear Headphones Black")
    assert _sony([walmart]).also_on_ebay is None and _sony([walmart]).offers == []


def test_cheaper_ebay_is_a_normal_offer_and_not_repeated() -> None:
    comp = _sony([_ebay(2199), _ebay(2599)])
    assert [o.merchant for o in comp.offers] == ["eBay"]
    assert comp.cheapest is not None and comp.cheapest.price_cents == 2199
    assert comp.also_on_ebay is None


def test_secondhand_and_liquidation_stores_are_not_store_prices() -> None:
    title = "Sony MDRZX110 Over-Ear Headphones Black"
    comp = _sony(
        [
            _offer("Liquidation125Plus", 1500, title),
            _offer("PayMore St Albert", 1600, title),
            _offer("K-W Surplus", 1700, title),
            _offer("Best Buy Canada", 2299, title),
        ]
    )
    assert [o.merchant for o in comp.offers] == ["Best Buy Canada"]


def test_a_part_number_split_by_a_hyphen_is_the_same_model() -> None:
    ref = "Sony MDRZX110 Over-Ear Headphones (Black)"
    assert _score(ref, "Sony MDR-ZX110 Wired On-Ear Headphones Black", 2498, 2699, "Sony") > 0.55
    # A genuinely different model is still rejected.
    assert _score(ref, "Sony MDR-ZX310 Wired On-Ear Headphones Black", 2498, 2699, "Sony") == 0.0


def test_a_barcode_match_does_not_depend_on_how_the_seller_words_the_title() -> None:
    odd_title = "ZX Series over ear headphones black NEW sealed"  # no brand, no model code
    comp = _sony([_ebay(2699, odd_title)])
    assert comp.also_on_ebay is not None and comp.also_on_ebay.match_confidence == 0.9

    # ...but a used unit or a multi-pack under the same barcode is not the product.
    assert _sony([_ebay(2699, "Sony MDR-ZX110 headphones used")]).also_on_ebay is None
    assert _sony([_ebay(2699, "Sony MDR-ZX110 headphones 2 Pack")]).also_on_ebay is None


def test_ebay_more_than_25_percent_under_amazon_is_never_shown() -> None:
    # $14.23 against Amazon's $24.98 (-43%): too cheap to be a genuine new unit,
    # and the barcode only proves what the seller typed.
    assert _sony([_ebay(1423)]).offers == []
    assert _sony([_ebay(1423)]).also_on_ebay is None
    # 25% under is the limit; 20% under is a normal, cheaper offer.
    assert _sony([_ebay(1873)]).offers == []
    comp = _sony([_ebay(1999)])
    assert [o.price_cents for o in comp.offers] == [1999]
    assert comp.cheapest is not None and comp.cheapest.merchant == "eBay"

    # The rule is eBay's alone: a confident store match at the same price stays.
    store = _offer("Best Buy Canada", 1700, "Sony MDRZX110 Over-Ear Headphones Black")
    assert [o.merchant for o in _sony([store]).offers] == ["Best Buy Canada"]


def test_an_unrelated_item_filed_under_the_products_catalogue_id_is_rejected() -> None:
    comp = build_comparison(
        reference_merchant="Amazon.ca",
        reference_title="LEGO Classic Medium Creative Brick Box 10696 Building Toy Set",
        reference_brand="LEGO",
        reference_price_cents=4193,
        currency="CAD",
        candidates=[
            ProviderOffer(
                provider="ebay",
                provider_product_id="B00NHQFA1I",
                merchant="eBay",
                price_cents=3999,  # inside the allowed price window on purpose
                currency="CAD",
                url="https://www.ebay.ca/itm/1",
                observed_at=datetime(2026, 10, 2, tzinfo=UTC),
                metadata={
                    "title": "New Lego 4x Black Arch 1 x 3 x 3 13965",
                    "matched_by": "epid",
                    "seller_feedback_pct": 99.9,
                    "seller_feedback_score": 5000,
                },
            )
        ],
    )
    assert comp.offers == [] and comp.also_on_ebay is None


# -- the store's own product page (a resolved Google Shopping row) ------------

INSTANT_POT = (
    "Instant Pot Duo 7-in-1 Electric Pressure Cooker, Slow Cooker, Rice Cooker, Steamer, "
    "Saute, Yogurt Maker, Warmer & Sterilizer, Stainless Steel, 6 Quart"
)
BESTBUY_8QT = (
    "https://www.bestbuy.ca/en-ca/product/instant-pot-duo-v5-7-in-1-pressure-cooker-8qt/16374909"
)
BESTBUY_6QT = (
    "https://www.bestbuy.ca/en-ca/product/instant-pot-duo-v5-7-in-1-pressure-cooker-6qt/16374908"
)


def test_store_page_words_reads_the_path_and_ignores_google_and_ebay() -> None:
    assert "pressure cooker 8qt" in store_page_words(BESTBUY_8QT)
    assert store_page_words("https://google.ca/search?ibp=oshop&q=instant+pot+8qt") == ""
    assert store_page_words("https://www.ebay.ca/itm/267667995506") == ""
    assert store_page_words(None) == ""


def test_store_page_for_another_size_is_a_conflict() -> None:
    assert store_page_conflict(INSTANT_POT, store_page_words(BESTBUY_8QT))
    assert not store_page_conflict(INSTANT_POT, store_page_words(BESTBUY_6QT))
    # "7-in-1" is not a size; a page that names no size is not a conflict
    assert not store_page_conflict(
        INSTANT_POT, store_page_words("https://www.walmart.ca/en/ip/instant-pot-duo-7-in-1/123")
    )
    # a slug writes 1.5 L as "1-5l"
    assert not store_page_conflict(
        "Hamilton Beach Kettle, 1.5 L", store_page_words("https://shop.example/p/kettle-1-5l")
    )
    assert store_page_conflict(
        "Hamilton Beach Kettle, 1.5 L", store_page_words("https://shop.example/p/kettle-1-7-l")
    )


def test_store_page_for_another_pack_count_is_a_conflict() -> None:
    single = "Crest Pro-Health Toothpaste 130 mL"
    assert store_page_conflict(single, store_page_words("https://shop.example/p/crest-3-pack"))
    assert not store_page_conflict(
        "Crest Pro-Health Toothpaste 130 mL, Pack of 3",
        store_page_words("https://shop.example/p/crest-pro-health-3-pack"),
    )


def test_store_page_in_another_colour_is_noted_not_dropped() -> None:
    bose = "Bose QuietComfort Headphones - Wireless Bluetooth Headphones, Black"
    white = store_page_words(
        "https://www.bestbuy.ca/en-ca/product/bose-quietcomfort-headphones-white/19184661"
    )
    assert not store_page_conflict(bose, white)
    assert store_page_colour_note(bose, white) == (
        "White at this store · the Amazon.ca price is for Black"
    )
    # same colour, or no colour on either side: nothing to say
    black = store_page_words("https://www.bestbuy.ca/en-ca/product/bose-quietcomfort-black/1")
    assert store_page_colour_note(bose, black) is None
    assert store_page_colour_note("Logitech M185 Wireless Mouse", white) is None


def test_build_comparison_drops_a_resolved_row_for_another_size() -> None:
    def offer(url: str) -> ProviderOffer:
        return ProviderOffer(
            provider="dataforseo",
            provider_product_id="B00FLYWNYQ",
            merchant="Best Buy Canada",
            price_cents=12999,
            currency="CAD",
            url=url,
            observed_at=datetime(2026, 10, 3, tzinfo=UTC),
            metadata={"title": "Instant Pot Duo 7-in-1 Electric Pressure Cooker"},
        )

    kwargs = dict(
        reference_merchant="Amazon.ca",
        reference_title=INSTANT_POT,
        reference_brand="Instant Pot",
        reference_price_cents=15999,
        currency="CAD",
    )
    google = "https://google.ca/search?ibp=oshop&q=Instant+Pot+Duo"
    assert len(build_comparison(candidates=[offer(google)], **kwargs).offers) == 1
    assert build_comparison(candidates=[offer(BESTBUY_8QT)], **kwargs).offers == []
    assert len(build_comparison(candidates=[offer(BESTBUY_6QT)], **kwargs).offers) == 1
