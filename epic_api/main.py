"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from epic_api import dependencies
from epic_api.errors import register_exception_handlers
from epic_api.routers import auth, contests, registrations, sessions, twins, users, ws
from epic_core.broadcaster import ContestBroadcaster
from epic_core.config import Settings, get_settings
from epic_core.db.base import create_all_tables
from epic_core.db.session import get_engine as get_db_engine
from epic_core.db.session import init_db
from epic_core.engine import SimulationEngine
from epic_twins.mechanical.plugin import register as register_mechanical


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings if hasattr(app.state, "settings") else get_settings()
    app.state.broadcaster = ContestBroadcaster(
        queue_capacity=settings.session_queue_capacity
    )
    app.state.engine = SimulationEngine(broadcaster=app.state.broadcaster)
    init_db(settings.database_url)
    await create_all_tables(get_db_engine())
    register_mechanical()
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    if settings is not None:
        app.state.settings = settings
        app.dependency_overrides[dependencies.get_settings] = lambda: settings

    register_exception_handlers(app)
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(contests.router, prefix="/api/v1")
    app.include_router(registrations.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(twins.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(ws.router, prefix="/api/v1/ws")
    return app
