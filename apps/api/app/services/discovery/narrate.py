"""Turn a deterministic price-check result into one plain-language paragraph.

The numbers and the verdict are already decided by the engine; the LLM only
phrases them. Disabled / any failure -> ``None``, and the caller shows the
structured card as usual.
"""

from __future__ import annotations

from app.core.settings import Settings
from app.services.decision.price_check import PriceCheckResult
from app.services.discovery.llm import ChatTransport, narrate_llm

_SYSTEM = (
    "You are a blunt, trustworthy shopping advisor. Given a product's buy/wait "
    "verdict and the supporting facts, write ONE short paragraph (2-4 sentences): "
    "say what the situation is, then what you'd do. Plain language, no hype, no "
    "emoji. Do not invent numbers — only use the facts given. Do not mention that "
    "you are an AI."
)


def _facts(result: PriceCheckResult) -> str:
    a = result.assessment
    lines = [
        f"Product: {result.title or result.provider_product_id}",
        f"Verdict: {a.verdict.value} (confidence {a.confidence.value})",
        f"Effective price: {a.effective_price.effective_cents / 100:.2f} {result.currency}",
    ]
    for reason in a.reasons[:5]:
        lines.append(f"- {reason}")
    if result.spread and result.spread.savings_vs_buy_box_cents > 0:
        s = result.spread
        lines.append(
            f"On Amazon itself, other sellers from "
            f"{s.lowest_overall_cents / 100:.2f} {s.currency} "
            f"({s.savings_vs_buy_box_cents / 100:.2f} under the buy box)."
        )
    if result.comparison and result.comparison.cheapest:
        c = result.comparison.cheapest
        lines.append(f"Cheaper at {c.merchant}: {c.price_cents / 100:.2f} {c.currency}.")
    return "\n".join(lines)


def narrate_check(
    result: PriceCheckResult,
    settings: Settings,
    *,
    transport: ChatTransport | None = None,
) -> str | None:
    return narrate_llm(settings, system=_SYSTEM, user=_facts(result), transport=transport)
