import hmac

from fastapi import Header, HTTPException, status

from app.core.settings import get_settings


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    # Constant-time compare — `!=` on a secret short-circuits on the first
    # differing byte, which is a textbook timing side-channel (CWE-208).
    if x_admin_token is None or not hmac.compare_digest(x_admin_token, settings.admin_api_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin token is required.",
        )
