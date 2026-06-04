"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from epic_api import dependencies
from epic_api.errors import register_exception_handlers
from epic_api.routers import auth, twins, users
from epic_core.config import Settings, get_settings
from epic_core.db.session import init_db
from epic_twins.mechanical.plugin import register as register_mechanical


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings if hasattr(app.state, "settings") else get_settings()
    init_db(settings.database_url)
    register_mechanical()
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    if settings is not None:
        app.state.settings = settings
        app.dependency_overrides[dependencies.get_settings] = lambda: settings

    register_exception_handlers(app)
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(twins.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    return app
