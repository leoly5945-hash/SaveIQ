"""Rank acquisition options by cost of ownership and surface the trade-offs.

Ordering is by ``effective_total_cents`` (lower is better). The profile never
silently reweights that number — instead it fires plain-language ``caveats`` so
the shopper sees exactly why the cheapest line might not be the right one.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.acquisition.models import AcquisitionOption, BuyerProfile
from app.services.acquisition.tco import TCOBreakdown, compute_tco

# Things SaveIQ structurally cannot know and the buyer must check themselves.
_ALWAYS_VERIFY = (
    "Current device price at each seller (launch-month and Black Friday move it most).",
    'The real throttle threshold on each "unlimited" plan tier.',
    "Whether your address actually gets full 5G on the carrier you would pick.",
)


class PathRecommendation(BaseModel):
    product_slug: str | None = None
    horizon_months: int
    ranked: list[TCOBreakdown]
    best_label: str
    runner_up_gap_cents: int  # how much more the second-cheapest path costs
    caveats: list[str] = Field(default_factory=list)
    verify_first: list[str] = Field(default_factory=list)


def _caveats(
    options: list[AcquisitionOption],
    ranked: list[TCOBreakdown],
    profile: BuyerProfile,
) -> list[str]:
    by_label = {o.label: o for o in options}
    out: list[str] = []
    best = ranked[0]
    best_opt = by_label.get(best.option_label)
    has_plan_choice = any(o.plan_monthly_cents > 0 for o in options)

    # 1. cheapest path leaves you owning nothing
    if not best.owns_at_horizon:
        out.append(
            f'"{best.option_label}" is cheapest on paper but you own nothing at the end. '
            "Only take it if you replace the device on that cycle anyway."
        )

    # 2. a lease/bundle return-path is in the set but the buyer keeps devices long
    churny = [
        o
        for o in options
        if o.returns_at_term
        and (
            profile.upgrades_every_months is None
            or profile.upgrades_every_months > o.term_months + 6
        )
    ]
    if churny and best_opt is not None and not best_opt.returns_at_term:
        out.append(
            "Bring-it-back / lease options were considered and rank poorly for you — "
            "you hold devices longer than their return cycle, so you'd pay the premium "
            "for flexibility you won't use."
        )

    # 3. lock-in on the recommended path
    if best_opt is not None and best_opt.lock_in_months > 0:
        out.append(
            f'"{best.option_label}" locks you in for {best_opt.lock_in_months} months; '
            "leaving early means settling the device balance in a lump."
        )

    # 4. service-sensitive buyer, cheapest path is a discount/MVNO carrier
    if profile.service_sensitivity == "high" and best_opt is not None and has_plan_choice:
        provider = (best_opt.provider or "").lower()
        flanker = any(
            k in provider for k in ("public mobile", "fizz", "chatr", "lucky", "freedom", "byod")
        )
        if flanker or best_opt.plan_monthly_cents == 0:
            out.append(
                "You flagged service quality as critical. The cheapest path here rides a "
                "discount / BYOD carrier — confirm its network and support match your bar "
                "before saving the ~difference."
            )

    # 5. business buyer — the support tier is the real lever (only when a carrier
    # plan is actually part of the decision)
    if profile.is_business and has_plan_choice:
        out.append(
            "As a business, a named account with priority support is often the highest-"
            "value item in this decision and is usually free to switch to — weigh it "
            "against the monthly premium, not just the sticker."
        )

    # 6. runner-up is close — the decision is not really about money
    if len(ranked) >= 2:
        gap = ranked[1].effective_total_cents - ranked[0].effective_total_cents
        if gap <= max(15000, ranked[0].effective_total_cents // 20):
            out.append(
                f'"{ranked[0].option_label}" and "{ranked[1].option_label}" are within '
                f"{gap / 100:.0f} over {profile.horizon_months} months — pick on lock-in, "
                "ownership, and support, not price."
            )
    return out


def compare_paths(
    options: list[AcquisitionOption],
    profile: BuyerProfile,
    *,
    product_slug: str | None = None,
) -> PathRecommendation:
    if not options:
        raise ValueError("compare_paths needs at least one acquisition option")

    ranked = sorted(
        (compute_tco(o, profile) for o in options),
        key=lambda t: t.effective_total_cents,
    )
    gap = (
        ranked[1].effective_total_cents - ranked[0].effective_total_cents if len(ranked) >= 2 else 0
    )
    return PathRecommendation(
        product_slug=product_slug,
        horizon_months=max(1, profile.horizon_months),
        ranked=ranked,
        best_label=ranked[0].option_label,
        runner_up_gap_cents=gap,
        caveats=_caveats(options, ranked, profile),
        verify_first=list(_ALWAYS_VERIFY),
    )
