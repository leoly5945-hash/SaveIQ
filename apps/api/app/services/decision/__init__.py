"""Deterministic commerce decision engine (CP9–CP11).

* CP9 `price_intelligence` — trailing-window stats + signals from a price series.
* CP10 `effective_price` — what the shopper actually pays (base + shipping + …).
* CP11 `deal_score` — a transparent 0–100 score and BUY / WAIT / FAIR verdict.

Everything here is pure and deterministic. There is no input for merchant
commission or affiliate payout anywhere in the scoring path.
"""

from app.services.decision.assess import assess_from_provider
from app.services.decision.deal_score import (
    Confidence,
    DealAssessment,
    Verdict,
    score_deal,
)
from app.services.decision.effective_price import (
    EffectivePrice,
    EffectivePriceComponent,
    compute_effective_price,
    effective_price_from_provider,
)
from app.services.decision.price_intelligence import (
    DEFAULT_WINDOWS,
    PriceIntelligence,
    WindowStat,
    summarize_history,
    summarize_points,
)

__all__ = [
    "DEFAULT_WINDOWS",
    "Confidence",
    "DealAssessment",
    "EffectivePrice",
    "EffectivePriceComponent",
    "PriceIntelligence",
    "Verdict",
    "WindowStat",
    "assess_from_provider",
    "compute_effective_price",
    "effective_price_from_provider",
    "score_deal",
    "summarize_history",
    "summarize_points",
]
