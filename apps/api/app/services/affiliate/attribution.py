"""Click-redirect attribution + conversion reconciliation.

Every outbound deal click goes through :func:`resolve_redirect`, which:

* generates a per-click ``click_id`` (also handed to the network as its SubID),
* writes an append-only :class:`AffiliateClickEvent` row server-side (so the
  log does not depend on a browser beacon surviving navigation),
* flags obvious bots / prefetches so they can be excluded from billable counts,
* de-dupes rapid repeat clicks, and
* returns the affiliate URL with the SubID appended in the param the network
  expects.

Networks then report conversions back via :func:`record_conversion` (S2S
postback or API pull); :func:`reconciliation_report` matches those against the
clicks we actually sent so payouts can be audited and disputed.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.models import (
    AffiliateClickEvent,
    AffiliateConversion,
    ClickTargetType,
    ConversionStatus,
    Merchant,
    MerchantListing,
    Offer,
    RecordStatus,
)
from app.services.user.identity import normalize_anonymous_user_id

# provider_source (our ingestion label) -> canonical network key.
NETWORK_BY_PROVIDER: dict[str, str] = {
    "mock_ca": "mock",
    "amazon_ca": "amazon",
    "amazon": "amazon",
    "rakuten": "rakuten",
    "impact": "impact",
    "cj": "cj",
    "awin": "awin",
    "skimlinks": "skimlinks",
    "sovrn": "sovrn",
    "flexoffers": "flexoffers",
}

# network key -> query param the network reads its SubID / click ref from.
SUBID_PARAM: dict[str, str] = {
    "amazon": "ascsubtag",
    "rakuten": "u1",
    "impact": "subId1",
    "cj": "sid",
    "awin": "clickref",
    "skimlinks": "xcust",
    "sovrn": "cuid",
    "flexoffers": "fobs",
    "mock": "subid",
}
DEFAULT_SUBID_PARAM = "subid"

_BOT_UA_MARKERS = (
    "bot",
    "crawl",
    "spider",
    "slurp",
    "curl/",
    "wget/",
    "python-requests",
    "python-httpx",
    "httpclient",
    "headless",
    "phantomjs",
    "lighthouse",
    "pingdom",
    "uptimerobot",
    "facebookexternalhit",
    "preview",
)

_CONVERSION_STATUS_ALIASES: dict[str, ConversionStatus] = {
    "pending": ConversionStatus.pending,
    "new": ConversionStatus.pending,
    "open": ConversionStatus.pending,
    "locked": ConversionStatus.pending,
    "approved": ConversionStatus.approved,
    "confirmed": ConversionStatus.approved,
    "closed": ConversionStatus.approved,
    "paid": ConversionStatus.approved,
    "validated": ConversionStatus.approved,
    "reversed": ConversionStatus.reversed,
    "rejected": ConversionStatus.reversed,
    "declined": ConversionStatus.reversed,
    "cancelled": ConversionStatus.reversed,
    "canceled": ConversionStatus.reversed,
    "returned": ConversionStatus.reversed,
}


@dataclass(frozen=True)
class RedirectResolution:
    target_url: str
    click_id: str
    network: str
    is_bot: bool
    reused: bool


def network_for_provider(provider_source: str) -> str:
    return NETWORK_BY_PROVIDER.get(provider_source, provider_source or "unknown")


def subid_param_for(network: str) -> str:
    return SUBID_PARAM.get(network, DEFAULT_SUBID_PARAM)


def looks_like_bot(
    user_agent: str | None,
    *,
    sec_purpose: str | None = None,
    purpose: str | None = None,
) -> bool:
    if (sec_purpose and "prefetch" in sec_purpose.lower()) or (
        purpose and "prefetch" in purpose.lower()
    ):
        return True
    if not user_agent:
        return True
    ua = user_agent.lower()
    return any(marker in ua for marker in _BOT_UA_MARKERS)


def hash_ip(ip: str | None, salt: str) -> str | None:
    if not ip:
        return None
    first = ip.split(",")[0].strip()
    if not first:
        return None
    return hashlib.sha256(f"{salt}:{first}".encode()).hexdigest()[:32]


def append_query_param(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    existing = parts.query
    addition = urlencode({key: value})
    query = f"{existing}&{addition}" if existing else addition
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _clip(value: str | None, length: int) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value[:length] or None


def resolve_redirect(
    db: Session,
    *,
    offer_id: int,
    target_type: str,
    user_agent: str | None,
    referrer: str | None,
    client_ip: str | None,
    anonymous_user_id: str | None,
    salt: str,
    dedup_seconds: int = 10,
    is_bot: bool = False,
) -> RedirectResolution | None:
    """Log the click and return the affiliate URL with our SubID attached.

    Returns ``None`` when the offer has no trackable destination.
    """
    if target_type not in {t.value for t in ClickTargetType}:
        target_type = ClickTargetType.affiliate.value

    row = db.execute(
        select(Offer, MerchantListing)
        .join(MerchantListing, Offer.merchant_listing_id == MerchantListing.id)
        .where(
            Offer.id == offer_id,
            Offer.record_status == RecordStatus.active.value,
            MerchantListing.record_status == RecordStatus.active.value,
        )
    ).one_or_none()
    if row is None:
        return None
    offer, listing = row

    base_url = listing.product_url
    if target_type == ClickTargetType.affiliate.value and offer.affiliate_link is not None:
        base_url = offer.affiliate_link.url
    if not base_url:
        base_url = listing.product_url
    if not base_url:
        return None

    anon = None
    if anonymous_user_id:
        try:
            anon = normalize_anonymous_user_id(anonymous_user_id)
        except ValueError:
            anon = None

    network = network_for_provider(offer.provider_source)
    ip_hash = hash_ip(client_ip, salt)

    # De-dupe: an equivalent click from the same actor in the last N seconds
    # reuses its click_id so we don't inflate counts or hand the network two
    # SubIDs for one intent.
    if dedup_seconds > 0 and (anon or ip_hash):
        cutoff = datetime.now(UTC) - timedelta(seconds=dedup_seconds)
        conditions = [
            AffiliateClickEvent.offer_id == offer.id,
            AffiliateClickEvent.target_type == target_type,
            AffiliateClickEvent.created_at >= cutoff,
            AffiliateClickEvent.click_id.is_not(None),
        ]
        if anon:
            conditions.append(AffiliateClickEvent.anonymous_user_id == anon)
        else:
            conditions.append(AffiliateClickEvent.ip_hash == ip_hash)
        prior = db.execute(
            select(AffiliateClickEvent)
            .where(*conditions)
            .order_by(AffiliateClickEvent.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if prior is not None and prior.landing_url:
            return RedirectResolution(
                target_url=prior.landing_url,
                click_id=prior.click_id or "",
                network=network,
                is_bot=prior.is_bot,
                reused=True,
            )

    click_id = uuid.uuid4().hex
    landing_url = append_query_param(base_url, subid_param_for(network), click_id)

    event = AffiliateClickEvent(
        offer_id=offer.id,
        merchant_id=listing.merchant_id,
        merchant_listing_id=listing.id,
        target_type=target_type,
        target_url=base_url[:2048],
        provider_source=offer.provider_source,
        source_record_id=offer.source_record_id,
        market=offer.market,
        user_agent=_clip(user_agent, 512),
        referrer=_clip(referrer, 2048),
        anonymous_user_id=anon,
        click_id=click_id,
        subid=click_id,
        network=network,
        landing_url=landing_url[:2048],
        ip_hash=ip_hash,
        is_bot=is_bot,
    )
    db.add(event)
    db.commit()

    return RedirectResolution(
        target_url=landing_url,
        click_id=click_id,
        network=network,
        is_bot=is_bot,
        reused=False,
    )


# --- Amazon clicks from price-check pages ------------------------------------------

AMAZON_CLICK_SOURCES = frozenset({"check", "checkbox", "image", "extension", "guide", "other"})
_AMAZON_PROVIDER = "amazon_ca"


def record_amazon_click(
    db: Session,
    *,
    asin: str,
    source: str,
    tag: str,
    user_agent: str | None,
    referrer: str | None,
    client_ip: str | None,
    salt: str,
    dedup_seconds: int = 10,
    is_bot: bool = False,
) -> RedirectResolution:
    """Log a click on a price-check page's Amazon button and return the buy URL.

    Price-check pages are not ``Offer`` rows, so their buy button used to link
    straight to Amazon and left no trace: most outbound clicks were never
    logged. The event has no ``offer_id``; the ASIN is ``source_record_id`` and
    the page type (``check``, ``checkbox`` …) is the ``subid``, which also rides
    to Amazon as ``ascsubtag``.
    """

    asin = asin.strip().upper()
    if source not in AMAZON_CLICK_SOURCES:
        source = "other"
    base_url = f"https://www.amazon.ca/dp/{asin}"
    landing_url = f"{base_url}?{urlencode({'tag': tag, 'ascsubtag': source})}"
    network = network_for_provider(_AMAZON_PROVIDER)
    ip_hash = hash_ip(client_ip, salt)

    if dedup_seconds > 0 and ip_hash:
        cutoff = datetime.now(UTC) - timedelta(seconds=dedup_seconds)
        prior = db.execute(
            select(AffiliateClickEvent)
            .where(
                AffiliateClickEvent.offer_id.is_(None),
                AffiliateClickEvent.source_record_id == asin,
                AffiliateClickEvent.ip_hash == ip_hash,
                AffiliateClickEvent.created_at >= cutoff,
            )
            .order_by(AffiliateClickEvent.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if prior is not None:
            return RedirectResolution(
                target_url=landing_url,
                click_id=prior.click_id or "",
                network=network,
                is_bot=prior.is_bot,
                reused=True,
            )

    click_id = uuid.uuid4().hex
    db.add(
        AffiliateClickEvent(
            offer_id=None,
            target_type=ClickTargetType.affiliate.value,
            target_url=base_url,
            provider_source=_AMAZON_PROVIDER,
            source_record_id=asin,
            market="CA",
            user_agent=_clip(user_agent, 512),
            referrer=_clip(referrer, 2048),
            click_id=click_id,
            subid=source,
            network=network,
            landing_url=landing_url,
            ip_hash=ip_hash,
            is_bot=is_bot,
        )
    )
    db.commit()
    return RedirectResolution(
        target_url=landing_url, click_id=click_id, network=network, is_bot=is_bot, reused=False
    )


# --- click report ---------------------------------------------------------------------


_OWN_HOST_SUFFIXES = ("saveiq.ca", "onrender.com", "localhost")


def _page_of(event: AffiliateClickEvent) -> str:
    """Where a click came from: a SaveIQ path, "(external: host)", or "(unknown)".

    Our own pages show up as a path ("/check/B0…", "/deal/slug"). A click that
    arrives from another site — e.g. a Facebook post linking straight to the
    hop — is named by that site instead of being mistaken for the homepage.
    Without a referrer, a price-check button still tells us its page through
    the ASIN and the button type it was logged with.
    """

    referrer = event.referrer
    if referrer:
        parts = urlsplit(referrer)
        host = (parts.hostname or "").lower()
        if host and not host.endswith(_OWN_HOST_SUFFIXES):
            return f"(external: {host.removeprefix('www.')})"
        path = parts.path or "/"
        return path if len(path) == 1 else path.rstrip("/")
    if event.offer_id is None and event.subid in ("check", "image"):
        return f"/check/{event.source_record_id}"
    return "(unknown)"


_PAGE_TYPES = frozenset(
    {"check", "deal", "deals", "guide", "category", "watchlist", "amazon-price-history"}
)


def _page_type(page: str) -> str:
    if page == "/":
        return "home"
    if page.startswith("(external"):
        return "external site"
    if page == "(unknown)":
        return "unknown"
    first = page.strip("/").split("/", 1)[0]
    return first if first in _PAGE_TYPES else "other"


def click_report(db: Session, *, days: int = 30, top: int = 15) -> dict[str, Any]:
    """Real (non-bot) outbound clicks by day, by the page they came from, and by product,
    each with the number of distinct visitors behind it."""

    since = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(
        select(AffiliateClickEvent, Offer.title)
        .outerjoin(Offer, AffiliateClickEvent.offer_id == Offer.id)
        .where(AffiliateClickEvent.created_at >= since)
        .order_by(AffiliateClickEvent.created_at)
    ).all()

    by_day: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_page: dict[str, int] = {}
    by_product: dict[str, int] = {}
    by_network: dict[str, int] = {}
    # Distinct visitors (hashed IP) behind each count: 15 clicks from one
    # visitor and 15 visitors with one click each are very different days.
    seen: dict[tuple[str, str], set[str]] = {}
    everyone: set[str] = set()
    without_visitor = 0
    bots = 0
    for event, title in rows:
        if event.is_bot:
            bots += 1
            continue
        created = (
            event.created_at if event.created_at.tzinfo else event.created_at.replace(tzinfo=UTC)
        )
        day = created.astimezone(UTC).date().isoformat()
        page = _page_of(event)
        product = title or event.source_record_id or "(unknown)"
        by_day[day] = by_day.get(day, 0) + 1
        by_type[_page_type(page)] = by_type.get(_page_type(page), 0) + 1
        by_page[page] = by_page.get(page, 0) + 1
        by_product[product] = by_product.get(product, 0) + 1
        net = event.network or "unknown"
        by_network[net] = by_network.get(net, 0) + 1
        if event.ip_hash:
            everyone.add(event.ip_hash)
            for group in (("day", day), ("page", page), ("product", product)):
                seen.setdefault(group, set()).add(event.ip_hash)
        else:
            without_visitor += 1

    def visitors(kind: str, name: str) -> int:
        return len(seen.get((kind, name), ()))

    def ranked(
        counts: dict[str, int], limit: int | None = None, kind: str | None = None
    ) -> list[dict[str, Any]]:
        items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        return [
            {"name": k, "clicks": v, **({"visitors": visitors(kind, k)} if kind else {})}
            for k, v in (items[:limit] if limit else items)
        ]

    return {
        "window_days": days,
        "since": since.isoformat(),
        "clicks": sum(by_day.values()),
        "visitors": len(everyone),
        # Clicks logged with no IP at all; they are in no visitor count.
        "clicks_without_visitor": without_visitor,
        "bot_clicks": bots,
        "by_day": [
            {"day": d, "clicks": c, "visitors": visitors("day", d)}
            for d, c in sorted(by_day.items())
        ],
        "by_page_type": ranked(by_type),
        "by_page": ranked(by_page, top, "page"),
        "by_product": ranked(by_product, top, "product"),
        "by_network": ranked(by_network),
    }


# --- conversion ingestion -------------------------------------------------------

# network -> where its postback/report payload carries each field. First hit wins.
_CONVERSION_FIELDS: dict[str, dict[str, tuple[str, ...]]] = {
    "_default": {
        "subid": ("subid", "sub_id", "sub1", "s2s_click_id", "u1", "sid", "clickref", "xcust"),
        "external_id": ("conversion_id", "transaction_id", "action_id", "id", "order_ref"),
        "order_id": ("order_id", "order_number", "oid"),
        "order_value": ("order_value", "sale_amount", "amount", "revenue", "total"),
        "commission": ("commission", "payout", "publisher_commission", "commission_amount"),
        "currency": ("currency", "currency_code"),
        "status": ("status", "state", "action_status"),
    },
}


def _first(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def _to_cents(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return None


def _map_status(value: Any) -> ConversionStatus:
    if value is None:
        return ConversionStatus.pending
    return _CONVERSION_STATUS_ALIASES.get(str(value).strip().lower(), ConversionStatus.pending)


def record_conversion(
    db: Session,
    *,
    network: str,
    payload: dict[str, Any],
) -> AffiliateConversion:
    fields = {**_CONVERSION_FIELDS["_default"], **_CONVERSION_FIELDS.get(network, {})}
    subid = _first(payload, fields["subid"])
    subid_str = str(subid).strip()[:80] if subid is not None else None
    external_id = _first(payload, fields["external_id"])
    external_str = str(external_id).strip()[:160] if external_id is not None else None

    click_event_id: int | None = None
    currency: str | None = None
    if subid_str:
        click = db.execute(
            select(AffiliateClickEvent).where(AffiliateClickEvent.click_id == subid_str).limit(1)
        ).scalar_one_or_none()
        if click is not None:
            click_event_id = click.id

    raw_currency = _first(payload, fields["currency"])
    if raw_currency:
        currency = str(raw_currency).strip().upper()[:3]

    conversion = AffiliateConversion(
        network=network[:64],
        subid=subid_str,
        click_event_id=click_event_id,
        external_id=external_str,
        order_id=(
            str(_first(payload, fields["order_id"])).strip()[:160]
            if _first(payload, fields["order_id"]) is not None
            else None
        ),
        status=_map_status(_first(payload, fields["status"])),
        order_value_cents=_to_cents(_first(payload, fields["order_value"])),
        commission_cents=_to_cents(_first(payload, fields["commission"])),
        currency=currency,
        reported_at=datetime.now(UTC),
        raw_payload=payload,
    )

    if external_str:
        existing = db.execute(
            select(AffiliateConversion).where(
                AffiliateConversion.network == network[:64],
                AffiliateConversion.external_id == external_str,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.status = conversion.status
            existing.order_value_cents = conversion.order_value_cents
            existing.commission_cents = conversion.commission_cents
            existing.currency = conversion.currency
            existing.click_event_id = existing.click_event_id or click_event_id
            existing.raw_payload = payload
            existing.reported_at = conversion.reported_at
            db.commit()
            return existing

    db.add(conversion)
    db.commit()
    return conversion


# --- reconciliation -----------------------------------------------------------


def reconciliation_report(db: Session, *, days: int = 30) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=days)

    click_rows = db.execute(
        select(
            AffiliateClickEvent.network,
            AffiliateClickEvent.merchant_id,
            func.count(AffiliateClickEvent.id),
            func.coalesce(func.sum(cast(AffiliateClickEvent.is_bot, Integer)), 0),
        )
        .where(AffiliateClickEvent.created_at >= since)
        .group_by(AffiliateClickEvent.network, AffiliateClickEvent.merchant_id)
    ).all()

    conv_rows = db.execute(
        select(
            AffiliateConversion.network,
            AffiliateClickEvent.merchant_id,
            AffiliateConversion.status,
            func.count(AffiliateConversion.id),
            func.coalesce(func.sum(AffiliateConversion.order_value_cents), 0),
            func.coalesce(func.sum(AffiliateConversion.commission_cents), 0),
        )
        .outerjoin(
            AffiliateClickEvent,
            AffiliateConversion.click_event_id == AffiliateClickEvent.id,
        )
        .where(AffiliateConversion.reported_at >= since)
        .group_by(
            AffiliateConversion.network,
            AffiliateClickEvent.merchant_id,
            AffiliateConversion.status,
        )
    ).all()

    merchants = {merchant.id: merchant.name for merchant in db.scalars(select(Merchant)).all()}

    buckets: dict[tuple[str | None, int | None], dict[str, Any]] = {}

    def bucket(network: str | None, merchant_id: int | None) -> dict[str, Any]:
        key = (network, merchant_id)
        if key not in buckets:
            buckets[key] = {
                "network": network or "unknown",
                "merchant_id": merchant_id,
                "merchant": merchants.get(merchant_id) if merchant_id else None,
                "clicks": 0,
                "bot_clicks": 0,
                "conversions": 0,
                "conversions_reversed": 0,
                "unmatched_conversions": 0,
                "order_value_cents": 0,
                "commission_cents": 0,
            }
        return buckets[key]

    for network, merchant_id, clicks, bot_clicks in click_rows:
        row = bucket(network, merchant_id)
        row["clicks"] += int(clicks or 0)
        row["bot_clicks"] += int(bot_clicks or 0)

    for network, merchant_id, status, count, order_value, commission in conv_rows:
        row = bucket(network, merchant_id)
        count = int(count or 0)
        if status == ConversionStatus.reversed.value:
            row["conversions_reversed"] += count
        else:
            row["conversions"] += count
            row["order_value_cents"] += int(order_value or 0)
            row["commission_cents"] += int(commission or 0)
        if merchant_id is None:
            row["unmatched_conversions"] += count

    report: list[dict[str, Any]] = []
    for row in buckets.values():
        billable = max(row["clicks"] - row["bot_clicks"], 0)
        row["billable_clicks"] = billable
        row["conversion_rate"] = round(row["conversions"] / billable, 4) if billable else 0.0
        row["epc_cents"] = round(row["commission_cents"] / billable, 2) if billable else 0.0
        row["discrepancy"] = (
            "no_conversions_despite_clicks" if billable >= 25 and row["conversions"] == 0 else None
        )
        report.append(row)

    report.sort(key=lambda r: r["clicks"], reverse=True)
    return {
        "window_days": days,
        "since": since.isoformat(),
        "rows": report,
        "totals": {
            "clicks": sum(r["clicks"] for r in report),
            "billable_clicks": sum(r["billable_clicks"] for r in report),
            "conversions": sum(r["conversions"] for r in report),
            "unmatched_conversions": sum(r["unmatched_conversions"] for r in report),
            "commission_cents": sum(r["commission_cents"] for r in report),
        },
    }
