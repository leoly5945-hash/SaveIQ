"""Admin: inspect registered product data providers (CP4).

Read-only. Confirms which providers are wired and configured on a deploy without
exposing any secret — the verification surface for ``KEEPA_API_KEY`` being set.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import require_admin
from app.providers import get_provider_registry

router = APIRouter(
    prefix="/admin/providers",
    tags=["admin-providers"],
    dependencies=[Depends(require_admin)],
)


class ProviderInfo(BaseModel):
    name: str
    market: str
    currency: str
    configured: bool
    capabilities: list[str]


class ProviderListResponse(BaseModel):
    count: int
    providers: list[ProviderInfo]


@router.get("", response_model=ProviderListResponse)
def list_providers() -> ProviderListResponse:
    registry = get_provider_registry()
    infos = [
        ProviderInfo(
            name=provider.name,
            market=provider.market,
            currency=provider.currency,
            configured=provider.is_configured(),
            capabilities=sorted(str(cap) for cap in provider.capabilities),
        )
        for provider in registry.list()
    ]
    infos.sort(key=lambda info: info.name)
    return ProviderListResponse(count=len(infos), providers=infos)
