"""CP9 — price intelligence.

Turns a raw price-history series into trailing-window statistics (7 / 30 / 90 /
180 days by default) plus a few derived signals the deal-score engine needs:
where the current price sits inside the 90-day range, whether it is an all-time
low, and how long it has been since the price was this low.

Pure functions over a list of ``(observed_at, price_cents)`` observations — no
database, no provider. The caller decides where the points come from (a live
``KeepaProvider.get_price_history`` result, or persisted ``price_history`` rows).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from app.providers.base import ProviderPriceHistory, ProviderPricePoint

DEFAULT_WINDOWS: tuple[int, ...] = (7, 30, 90, 180)

# Preference order when the caller does not pin a series kind.
_SERIES_PREFERENCE: tuple[str, ...] = ("buy_box", "amazon", "new", "used")


class WindowStat(BaseModel):
    """Summary of one trailing window."""

    days: int
    sample_count: int
    min_cents: int | None = None
    max_cents: int | None = None
    avg_cents: int | None = None
    median_cents: int | None = None


class PriceIntelligence(BaseModel):
    """Windowed statistics + derived signals for a single price series."""

    currency: str
    series_kind: str
    total_points: int
    covers_from: datetime | None = None
    covers_to: datetime | None = None
    coverage_days: int = 0
    current_cents: int | None = None
    windows: dict[int, WindowStat] = Field(default_factory=dict)
    all_time_min_cents: int | None = None
    all_time_max_cents: int | None = None
    # 0.0 = current is the cheapest seen in 90d, 1.0 = the most expensive.
    current_percentile_90d: float | None = None
    is_all_time_low: bool = False
    # Trading days-equivalent: calendar days since the series was last <= current.
    days_since_price_this_low: int | None = None
    # How many distinct observations in 90d were <= current * 1.02.
    times_this_low_90d: int = 0
    # Real provider price *changes* in the window / over the product's whole life
    # — distinct from ``total_points``, which for Keepa is a densified daily fill.
    source_observations: int | None = None
    lifetime_observations: int | None = None
    # Provider-computed stats (e.g. Keepa avg30/avg90/avg180 + min/max), which use
    # the provider's full data rather than our window. Authoritative when present.
    provider_stats: dict[str, int | None] = Field(default_factory=dict)

    def window(self, days: int) -> WindowStat | None:
        return self.windows.get(days)


def _median(values: Sequence[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) // 2


def _select_series(
    points: Iterable[ProviderPricePoint],
    *,
    prefer_kind: str | None,
) -> tuple[str, list[ProviderPricePoint]]:
    """Pick one coherent series from a mixed-kind list of points.

    Uses ``prefer_kind`` when it has any points, otherwise the first kind in
    ``_SERIES_PREFERENCE`` that does, otherwise whatever is most common.
    """

    by_kind: dict[str, list[ProviderPricePoint]] = {}
    for point in points:
        by_kind.setdefault(point.kind, []).append(point)
    if not by_kind:
        return (prefer_kind or "unknown", [])

    order: list[str] = []
    if prefer_kind:
        order.append(prefer_kind)
    order.extend(k for k in _SERIES_PREFERENCE if k not in order)
    order.extend(k for k in by_kind if k not in order)

    for kind in order:
        series = by_kind.get(kind)
        if series:
            series.sort(key=lambda p: p.observed_at)
            return (kind, series)
    return (prefer_kind or "unknown", [])


def summarize_points(
    points: Sequence[ProviderPricePoint],
    *,
    currency: str,
    current_cents: int | None = None,
    prefer_kind: str | None = None,
    windows: Sequence[int] = DEFAULT_WINDOWS,
    now: datetime | None = None,
    source_observations: int | None = None,
    lifetime_observations: int | None = None,
    provider_stats: dict[str, int | None] | None = None,
) -> PriceIntelligence:
    """Build :class:`PriceIntelligence` from mixed-kind price points."""

    now = now or datetime.now(tz=UTC)
    stats = {k: v for k, v in (provider_stats or {}).items() if v is not None}
    kind, series = _select_series(points, prefer_kind=prefer_kind)

    if not series:
        return PriceIntelligence(
            currency=currency,
            series_kind=kind,
            total_points=0,
            current_cents=current_cents,
            windows={int(d): WindowStat(days=int(d), sample_count=0) for d in windows},
            source_observations=source_observations,
            lifetime_observations=lifetime_observations,
            provider_stats=stats,
        )

    prices_all = [p.price_cents for p in series]
    covers_from = series[0].observed_at
    covers_to = series[-1].observed_at
    # When the caller does not pass an explicit current price, use the last
    # observation on the series.
    effective_current = current_cents if current_cents is not None else prices_all[-1]

    window_stats: dict[int, WindowStat] = {}
    for days in windows:
        cutoff = now - timedelta(days=int(days))
        vals = [p.price_cents for p in series if p.observed_at >= cutoff]
        window_stats[int(days)] = WindowStat(
            days=int(days),
            sample_count=len(vals),
            min_cents=min(vals) if vals else None,
            max_cents=max(vals) if vals else None,
            avg_cents=round(sum(vals) / len(vals)) if vals else None,
            median_cents=_median(vals),
        )

    window_90 = [p.price_cents for p in series if p.observed_at >= now - timedelta(days=90)]
    percentile_90d: float | None = None
    times_low_90d = 0
    if window_90 and effective_current is not None:
        # Fraction of 90-day observations strictly cheaper than the current price:
        # 0.0 => nothing was cheaper (current is the best seen), 1.0 => all cheaper.
        strictly_below = sum(1 for v in window_90 if v < effective_current)
        percentile_90d = round(strictly_below / len(window_90), 4)
        times_low_90d = sum(1 for v in window_90 if v <= round(effective_current * 1.02))

    all_time_min = min(prices_all)
    all_time_max = max(prices_all)
    is_all_time_low = effective_current is not None and effective_current <= round(
        all_time_min * 1.005
    )

    days_since_this_low: int | None = None
    if effective_current is not None:
        for point in reversed(series[:-1]):
            if point.price_cents <= effective_current:
                days_since_this_low = max((now - point.observed_at).days, 0)
                break

    return PriceIntelligence(
        currency=currency,
        series_kind=kind,
        total_points=len(series),
        covers_from=covers_from,
        covers_to=covers_to,
        coverage_days=max((covers_to - covers_from).days, 0),
        current_cents=effective_current,
        windows=window_stats,
        all_time_min_cents=all_time_min,
        all_time_max_cents=all_time_max,
        current_percentile_90d=percentile_90d,
        is_all_time_low=is_all_time_low,
        days_since_price_this_low=days_since_this_low,
        times_this_low_90d=times_low_90d,
        source_observations=source_observations,
        lifetime_observations=lifetime_observations,
        provider_stats=stats,
    )


def summarize_history(
    history: ProviderPriceHistory,
    *,
    current_cents: int | None = None,
    prefer_kind: str | None = None,
    windows: Sequence[int] = DEFAULT_WINDOWS,
    now: datetime | None = None,
) -> PriceIntelligence:
    """Convenience wrapper over :func:`summarize_points` for a provider result.

    Threads the provider's own metadata (base series kind, real observation
    counts, precomputed stats) through so the score engine can prefer it.
    """

    meta = history.metadata or {}
    keepa_stats = meta.get("keepa_stats")
    provider_stats = keepa_stats if isinstance(keepa_stats, dict) else None
    return summarize_points(
        history.points,
        currency=history.currency,
        current_cents=current_cents,
        prefer_kind=prefer_kind or meta.get("base_kind"),
        windows=windows,
        now=now,
        source_observations=meta.get("source_observations"),
        lifetime_observations=meta.get("lifetime_observations"),
        provider_stats=provider_stats,
    )
