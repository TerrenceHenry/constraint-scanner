from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from constraint_scanner.api.routes.controls import router as controls_router
from constraint_scanner.api.routes.health import router as health_router
from constraint_scanner.api.routes.markets import router as markets_router
from constraint_scanner.api.routes.opportunities import router as opportunities_router
from constraint_scanner.api.routes.simulations import router as simulations_router
from constraint_scanner.control_runtime import RuntimeControlState
from constraint_scanner.config.loader import get_settings
from constraint_scanner.config.models import Settings
from constraint_scanner.core.logging import configure_logging
from constraint_scanner.db.session import get_engine, make_session_factory
from constraint_scanner.ingestion.feed_state import FeedState
from constraint_scanner.risk.kill_switch import KillSwitch
from constraint_scanner.runtime import ServiceRuntime
from constraint_scanner.trading.mode_state import TradingModeState


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    session_factory: sessionmaker[Session] | None = None,
    feed_state: FeedState | None = None,
    service_runtime: ServiceRuntime | None = None,
    runtime_controls: RuntimeControlState | None = None,
    kill_switch: KillSwitch | None = None,
    trading_mode_state: TradingModeState | None = None,
) -> FastAPI:
    active_settings = settings or get_settings()
    configure_logging(active_settings.app.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if service_runtime is not None:
            application.state.service_runtime = service_runtime
            application.state.engine = service_runtime.engine
            application.state.session_factory = service_runtime.session_factory
            application.state.feed_state = service_runtime.feed_state
            application.state.runtime_controls = service_runtime.runtime_controls
            application.state.kill_switch = service_runtime.runtime_controls.kill_switch
            application.state.trading_mode_state = service_runtime.runtime_controls.trading_mode_state
            yield
            await service_runtime.aclose()
            return

        active_engine = engine
        owns_engine = False
        if active_engine is None and session_factory is None:
            active_engine = get_engine(
                url=active_settings.database.sqlalchemy_url(),
                echo=active_settings.database.echo,
            )
            owns_engine = True

        active_session_factory = session_factory or make_session_factory(active_engine)
        application.state.engine = active_engine
        application.state.session_factory = active_session_factory
        application.state.feed_state = feed_state or FeedState(
            stale_after_seconds=active_settings.ingestion.stale_after_seconds
        )
        default_runtime_controls = RuntimeControlState.from_settings(active_settings)
        active_runtime_controls = runtime_controls or RuntimeControlState(
            kill_switch=kill_switch or default_runtime_controls.kill_switch,
            trading_mode_state=trading_mode_state or default_runtime_controls.trading_mode_state,
        )
        application.state.runtime_controls = active_runtime_controls
        application.state.kill_switch = active_runtime_controls.kill_switch
        application.state.trading_mode_state = active_runtime_controls.trading_mode_state
        yield
        if owns_engine and active_engine is not None:
            active_engine.dispose()

    application = FastAPI(
        title=active_settings.app.name,
        version=active_settings.app.version,
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.service_runtime = service_runtime
    application.include_router(health_router)
    application.include_router(markets_router)
    application.include_router(opportunities_router)
    application.include_router(simulations_router)
    application.include_router(controls_router)
    return application
