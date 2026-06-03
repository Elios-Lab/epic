"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from epic_api import dependencies
from epic_api.errors import register_exception_handlers
from epic_api.routers import twins
from epic_core.config import Settings
from epic_twins.mechanical.plugin import register as register_mechanical


@asynccontextmanager
async def lifespan(app: FastAPI):
    register_mechanical()
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    if settings is not None:
        app.dependency_overrides[dependencies.get_settings] = lambda: settings

    register_exception_handlers(app)
    app.include_router(twins.router, prefix="/api/v1")
    return app

