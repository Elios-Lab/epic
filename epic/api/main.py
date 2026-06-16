"""FastAPI application factory."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from epic.api import dependencies
from epic.api.dependencies import build_notification_service
from epic.api.errors import register_exception_handlers
from epic.api.routers import (
    admin_environment,
    auth,
    catalog,
    contests,
    invitations,
    leaderboard,
    organizer_requests,
    registrations,
    sessions,
    submissions,
    templates,
    twins,
    users,
    ws,
)
from epic.core.broadcaster import ContestBroadcaster
from epic.core.config import Settings, get_settings
from epic.core.db.bootstrap import seed_admin
from epic.core.db.models import Contest, SimulationSession, Submission, User
from epic.core.notifications import NotificationService, SessionAutoPaused
from epic.core.db.session import get_session_factory
from epic.core.db.session import init_db
from epic.core.engine import SimulationEngine
from epic.core.evaluators import ForecastingEvaluator
from epic.core.session_tasks import SessionTaskRegistry
import epic.core.registry as registry_module
from epic.core.scoring import F1Score, MAE
from epic.sensors.plugin import register as register_sensors
from epic.twins.electric_motor.plugin import register as register_electric_motor
from epic.twins.industrial_pump.plugin import register as register_industrial_pump
from epic.twins.mass_spring_damper.plugin import register as register_mass_spring_damper
from epic.twins.rotating_machinery.plugin import register as register_rotating_machinery
from epic.twins.smart_building.plugin import register as register_smart_building

GUI_DIR = Path(__file__).resolve().parent.parent / "gui"
GUI_DIST_DIR = GUI_DIR / "dist"
NOTEBOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "notebooks"


def get_gui_dir() -> Path:
    """Return built GUI assets when available, otherwise source assets."""
    if (GUI_DIST_DIR / "index.html").exists():
        return GUI_DIST_DIR
    return GUI_DIR


async def _recover_after_restart(notifications: NotificationService) -> None:
    """Repair state left inconsistent by an unclean shutdown.

    Two things can be wrong after a crash:
    - Sessions marked RUNNING with no engine actually running.
      We pause them (and the owning contest) so organizers can resume manually.
    - Submissions stuck in PENDING because their scoring task died in memory.
      We reschedule their scoring so they eventually reach EVALUATED or FAILED.
    """
    db_factory = get_session_factory()
    async with db_factory() as db:
        # ── 1. Orphaned running sessions ─────────────────────────────────────
        orphaned_result = await db.execute(
            select(SimulationSession).where(
                SimulationSession.status.in_(["RUNNING", "CREATED"])
            )
        )
        paused_notices: list[SessionAutoPaused] = []
        for session in orphaned_result.scalars():
            contest_result = await db.execute(
                select(Contest).where(Contest.id == session.contest_id)
            )
            contest = contest_result.scalar_one_or_none()
            if contest is None or contest.status != "ACTIVE":
                continue
            contest.status = "PAUSED"
            session.status = "PAUSED"
            session.ended_at = datetime.now(timezone.utc)
            session.session_metadata = {
                **(session.session_metadata or {}),
                "recovery": "Paused automatically after unclean server shutdown. Use Resume to restart.",
            }
            # Alert the owner and all administrators so someone resumes it.
            recipients: dict[str, None] = {}
            if contest.created_by is not None:
                owner_result = await db.execute(
                    select(User).where(User.id == contest.created_by)
                )
                owner = owner_result.scalar_one_or_none()
                if owner is not None:
                    recipients[owner.email] = None
            admins_result = await db.execute(
                select(User).where(User.role == "ADMINISTRATOR", User.status == "ACTIVE")
            )
            for admin in admins_result.scalars():
                recipients[admin.email] = None
            paused_notices.extend(
                SessionAutoPaused(to_email=email, contest_name=contest.name)
                for email in recipients
            )
        await db.commit()
        for notice in paused_notices:
            await notifications.notify(notice)

        # ── 2. Orphaned PENDING submissions ───────────────────────────────────
        pending_result = await db.execute(
            select(Submission).where(Submission.status == "PENDING")
        )
        pending_ids = [sub.id for sub in pending_result.scalars()]

    for submission_id in pending_ids:
        asyncio.create_task(
            submissions._score_submission(submission_id, db_factory),
            name=f"epic-score-{submission_id}",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings if hasattr(app.state, "settings") else get_settings()
    app.state.settings = settings
    if settings.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("epic").setLevel(logging.DEBUG)
    app.state.broadcaster = ContestBroadcaster(
        queue_capacity=settings.session_queue_capacity
    )
    app.state.session_tasks = SessionTaskRegistry(settings.max_concurrent_sessions)
    notification_service = build_notification_service(settings)
    app.state.engine = SimulationEngine(
        broadcaster=app.state.broadcaster,
        notification_service=notification_service,
    )
    init_db(settings.database_url)
    async with get_session_factory()() as db:
        await seed_admin(settings, db)
    register_sensors()
    register_mass_spring_damper()
    register_industrial_pump()
    register_electric_motor()
    register_smart_building()
    register_rotating_machinery()
    if not registry_module.metric_registry.contains("mae"):
        registry_module.metric_registry.register(MAE())
    if not registry_module.metric_registry.contains("f1"):
        registry_module.metric_registry.register(F1Score())
    if not registry_module.task_evaluator_registry.contains("FORECASTING"):
        registry_module.task_evaluator_registry.register(ForecastingEvaluator())
    await _recover_after_restart(notification_service)
    yield
    # Graceful shutdown: cancel background simulation and scoring tasks so
    # their database sessions close cleanly instead of being killed with
    # checked-out connections (which leaks and warns at garbage collection).
    await app.state.session_tasks.cancel_all()
    background = [
        task
        for task in asyncio.all_tasks()
        if task is not asyncio.current_task()
        and task.get_name().startswith("epic-")
    ]
    for task in background:
        task.cancel()
    if background:
        await asyncio.gather(*background, return_exceptions=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="EPIC API",
        description="ELIOS Predictive Intelligence Challenge — simulation-driven machine learning competition platform.",
        version="1.0.0",
        redoc_url=None,
        lifespan=lifespan,
    )
    if settings is not None:
        app.state.settings = settings
        app.dependency_overrides[dependencies.get_settings] = lambda: settings

    register_exception_handlers(app)
    app.include_router(admin_environment.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(catalog.router, prefix="/api/v1")
    app.include_router(contests.router, prefix="/api/v1")
    app.include_router(invitations.router, prefix="/api/v1")
    app.include_router(leaderboard.router, prefix="/api/v1")
    app.include_router(organizer_requests.router, prefix="/api/v1")
    app.include_router(registrations.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(submissions.router, prefix="/api/v1")
    app.include_router(templates.router, prefix="/api/v1")
    app.include_router(twins.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(ws.router, prefix="/api/v1/ws")

    # SPA deep links (e.g. /register?token=… from invitation emails) must
    # serve the single-page app; routes registered before the static mount
    # take precedence over it.
    @app.get("/register", include_in_schema=False)
    async def spa_register():
        return FileResponse(get_gui_dir() / "index.html")

    @app.get("/notebooks/quickstart.ipynb", include_in_schema=False)
    async def quickstart_notebook():
        return FileResponse(
            NOTEBOOKS_DIR / "quickstart.ipynb",
            media_type="application/x-ipynb+json",
        )

    app.mount("/", StaticFiles(directory=get_gui_dir(), html=True), name="gui")
    return app
