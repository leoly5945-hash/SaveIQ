from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.admin_abtest import router as admin_abtest_router
from app.api.routes.admin_affiliate import router as admin_affiliate_router
from app.api.routes.admin_bandit import router as admin_bandit_router
from app.api.routes.admin_canary import router as admin_canary_router
from app.api.routes.admin_gate9 import router as admin_gate9_router
from app.api.routes.admin_rate_limit import router as admin_rate_limit_router
from app.api.routes.admin_router import router as admin_router_status
from app.api.routes.admin_safety import router as admin_safety_router
from app.api.routes.admin_users import router as admin_users_router
from app.api.routes.bandit import router as bandit_router
from app.api.routes.clicks import router as clicks_router
from app.api.routes.health import router as health_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.personalization import router as personalization_router
from app.api.routes.recommendations import router as recommendations_router
from app.api.routes.search import router as search_router
from app.api.routes.user import router as user_router
from app.core.logging import configure_logging
from app.core.settings import get_settings
from app.middleware.abtest import ABTestMiddleware
from app.middleware.canary import CanaryMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(
        structured=settings.structured_logging,
        log_level=settings.log_level,
    )
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Last added = outermost. Cohort middlewares wrap logging so labels survive metrics.
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(ABTestMiddleware)
    app.add_middleware(CanaryMiddleware)
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(clicks_router)
    app.include_router(search_router)
    app.include_router(recommendations_router)
    app.include_router(bandit_router)
    app.include_router(personalization_router)
    app.include_router(user_router)
    app.include_router(admin_affiliate_router)
    app.include_router(admin_router_status)
    app.include_router(admin_bandit_router)
    app.include_router(admin_users_router)
    app.include_router(admin_gate9_router)
    app.include_router(admin_rate_limit_router)
    app.include_router(admin_canary_router)
    app.include_router(admin_abtest_router)
    app.include_router(admin_safety_router)
    return app


app = create_app()
