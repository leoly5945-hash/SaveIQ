from fastapi import APIRouter
from pydantic import BaseModel

from app.core.settings import get_settings
from app.providers.amazon_creators import get_creators_client

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )


class IntegrationsResponse(BaseModel):
    amazon_images: str
    ebay_offers: str


@router.get("/health/integrations", response_model=IntegrationsResponse)
def integrations() -> IntegrationsResponse:
    """Whether the optional integrations are switched on and answering.

    Coarse states only (``not_configured`` / ``untried`` / ``ok`` / ``error: …``
    with the provider's status and error code) — never a credential.
    """

    settings = get_settings()
    creators = get_creators_client(settings)
    ebay_on = bool(settings.ebay_client_id and settings.ebay_client_secret)
    return IntegrationsResponse(
        amazon_images=creators.status() if creators is not None else "not_configured",
        ebay_offers="configured" if ebay_on else "not_configured",
    )
