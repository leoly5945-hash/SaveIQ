"""Public discovery endpoint (Layer 3, entry).

No auth, per-IP rate limited hard (``DISCOVER_RATE_PER_MINUTE``, default 6) — it
spends a Keepa search plus a few price calls. A natural-language request in,
candidate products out; the shopper then clicks through to ``/check`` for the
verdict.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.settings import Settings, get_settings
from app.providers import get_provider_registry
from app.services.discovery import DiscoverResult, discover, parse_shopping_query
from app.services.endpoint_limit import allow

router = APIRouter(prefix="/discover", tags=["discover"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("", response_model=DiscoverResult)
async def discover_products(
    request: Request,
    q: Annotated[str, Query(min_length=2, max_length=240, description="what you want, in words")],
    limit: Annotated[int, Query(ge=1, le=12)] = 8,
) -> DiscoverResult:
    settings: Settings = get_settings()
    if not allow("discover", _client_ip(request), per_minute=settings.discover_rate_per_minute):
        raise HTTPException(status_code=429, detail="too many searches — try again in a minute")

    try:
        query = parse_shopping_query(q, settings=settings)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return await discover(get_provider_registry(), query, limit=limit)
