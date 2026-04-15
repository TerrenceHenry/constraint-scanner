from __future__ import annotations

from fastapi import FastAPI

from constraint_scanner.api.routes.health import router as health_router
from constraint_scanner.config.loader import get_settings
from constraint_scanner.config.models import Settings
from constraint_scanner.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    configure_logging(active_settings.app.log_level)

    application = FastAPI(
        title=active_settings.app.name,
        version=active_settings.app.version,
    )
    application.state.settings = active_settings
    application.include_router(health_router)
    return application

