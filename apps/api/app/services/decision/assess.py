"""Orchestrator: provider price + history -> full deal assessment (CP9–CP11)."""

from __future__ import annotations

from datetime import datetime

from app.providers.base import ProviderOffer, ProviderPrice, ProviderPriceHistory
from app.services.decision.deal_score import DealAssessment, Verdict, score_deal
from app.services.decision.effective_price import (
    EffectivePrice,
    compute_effective_price,
    effective_price_from_provider,
)
from app.services.decision.price_intelligence import (
    PriceIntelligence,
    summarize_history,
)

# Map a ProviderPrice.source ("keepa:buy_box") to a history series kind ("buy_box").
_SOURCE_TO_KIND: dict[str, str] = {
    "keepa:buy_box": "buy_box",
    "keepa:amazon": "amazon",
    "keepa:new": "new",
}


def assess_from_provider(
    price: ProviderPrice,
    history: ProviderPriceHistory,
    *,
    offer: ProviderOffer | None = None,
    now: datetime | None = None,
) -> DealAssessment | None:
    """Run CP9→CP10→CP11 over one provider's price + history.

    Returns ``None`` only when there is no current price to assess at all.
    """

    effective: EffectivePrice | None = effective_price_from_provider(price, offer=offer)
    if effective is None:
        return None

    prefer_kind = _SOURCE_TO_KIND.get(price.source)
    intelligence: PriceIntelligence = summarize_history(
        history,
        current_cents=effective.effective_cents,
        prefer_kind=prefer_kind,
        now=now,
    )
    return score_deal(effective, intelligence)


__all__ = [
    "DealAssessment",
    "EffectivePrice",
    "PriceIntelligence",
    "Verdict",
    "assess_from_provider",
    "compute_effective_price",
    "score_deal",
    "summarize_history",
]
