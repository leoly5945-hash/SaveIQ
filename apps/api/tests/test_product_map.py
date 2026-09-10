"""Mapping a resolved Amazon product onto the acquisition taxonomy."""

from __future__ import annotations

import pytest

from app.services.acquisition.product_map import infer_product_context


@pytest.mark.parametrize(
    ("category", "title", "expected_cat", "expected_tier"),
    [
        ("Cell Phones", "Apple iPhone 17 Pro 256GB", "smartphone", "flagship"),
        ("Unlocked Cell Phones", "Samsung Galaxy S26 FE", "smartphone", "midrange"),
        ("Laptop Computers", 'Apple MacBook Air 15"', "laptop", "flagship"),
        ("OLED TVs", 'LG OLED evo C5 65"', "television", "flagship"),
        ("Over-Ear Headphones", "Sony WH-1000XM6", "headphones", "flagship"),
        ("French Door Refrigerators", "Samsung 28 cu ft Fridge", "major_appliance", "flagship"),
        ("Garden Hand Tools", "Fiskars Pruner", "general", "flagship"),
        (None, "Random Gizmo 3000", "general", "flagship"),
    ],
)
def test_category_inference(
    category: str | None, title: str, expected_cat: str, expected_tier: str
) -> None:
    ctx = infer_product_context(price_cents=50000, category=category, brand="acme", title=title)
    assert ctx.category == expected_cat
    assert ctx.tier == expected_tier
    assert ctx.retail_price_cents == 50000


def test_brand_is_lowercased_and_blank_becomes_none() -> None:
    assert (
        infer_product_context(
            price_cents=1, category="Laptop Computers", brand="ASUS", title="x"
        ).brand
        == "asus"
    )
    assert (
        infer_product_context(
            price_cents=1, category="Laptop Computers", brand="  ", title="x"
        ).brand
        is None
    )
