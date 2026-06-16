"""Domain-independent simulation engine."""

from __future__ import annotations

import asyncio
import copy
import random
from datetime import datetime, timedelta, timezone
from uuid import UUID

import numpy as np
from sqlalchemy import func, select

import epic_core.kernel.registry as registry_module
from epic_core.kernel.broadcaster import ContestBroadcaster
from epic_core.kernel.db.models import (
    Contest,
    ContestRegistration,
    SensorObservation,
    SimulationSession,
    User,
)
from epic_core.kernel.exceptions import PluginExecutionError, PluginNotFoundError
from epic_core.kernel.notifications import (
    NotificationService,
    SessionFailed,
    SubmissionWindowOpen,
)


class SimulationEngine:
    def __init__(
        self,
        broadcaster: ContestBroadcaster | None = None,
        notification_service: NotificationService | None = None,
    ) -> None:
        self._broadcaster = broadcaster
        self._notifications = notification_service

    async def run_session(self, session_id: str, db_factory) -> None:
        async with db_factory() as db:
            session = await self._load_session(db, session_id)
            session.status = "RUNNING"
            session.started_at = datetime.now(timezone.utc)
            await db.commit()

            try:
                await self._run_loop(session, db_factory)
            except Exception as exc:
                async with db_factory() as db2:
                    session2 = await self._load_session(db2, session_id)
                    session2.status = "FAILED"
                    session2.session_metadata = {
                        **(session2.session_metadata or {}),
                        "error": str(exc),
                    }
                    session2.ended_at = datetime.now(timezone.utc)
                    await db2.commit()
                await self._notify_session_failed(db_factory, session2, str(exc))
                return

    async def _load_session(self, db, session_id: str) -> SimulationSession:
        result = await db.execute(
            select(SimulationSession).where(SimulationSession.id == UUID(session_id))
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise PluginExecutionError(f"session '{session_id}' does not exist")
        return session

    async def _run_loop(self, session: SimulationSession, db_factory) -> None:
        async with db_factory() as db:
            contest = await self._load_contest(db, session.contest_id)

        try:
            twin = copy.deepcopy(registry_module.twin_registry.get(session.twin_id))
        except PluginNotFoundError as exc:
            raise PluginExecutionError(
                f"twin '{session.twin_id}' could not be loaded"
            ) from exc

        # Per-session RNG: injected into sensors that accept it, so that
        # concurrent sessions never share random state. The global seeding
        # is kept as a fallback for plugins using module-level RNG functions.
        if session.seed is not None:
            random.seed(session.seed)
            np.random.seed(session.seed)
            session_rng = random.Random(session.seed)
        else:
            session_rng = random.Random()

        supported = twin.supported_quantities()
        contest_sensors = []
        for cfg in contest.sensor_configs:
            contest_sensors.append(
                self._build_configured_sensor(cfg, twin, supported, session_rng)
            )

        available_faults = {fault.fault_id for fault in twin.get_faults()}
        for entry in contest.fault_schedule:
            fault_id = entry.get("fault_id")
            if fault_id not in available_faults:
                raise PluginExecutionError(
                    f"fault '{fault_id}' is not available for twin '{twin.twin_id}'"
                )

        state = self._call_plugin(
            twin.twin_id,
            "configure",
            twin.configure,
            contest.initial_conditions,
            contest.fault_schedule,
        )

        dt = 1.0 / session.sampling_rate_hz
        commit_interval = 10   # commit every 10 steps (≤1 s at 10 Hz, 0.5 s at 20 Hz)

        # ── Two-phase setup ───────────────────────────────────────────
        two_phase = (
            contest.end_of_observation is not None
            and contest.prediction_horizon_seconds is not None
        )
        if two_phase:
            end_of_observation_utc = self._as_utc(contest.end_of_observation)
            simulation_end = end_of_observation_utc + timedelta(
                seconds=contest.prediction_horizon_seconds
            )
            eval_n_steps = round(
                contest.prediction_horizon_seconds * session.sampling_rate_hz
            )
        else:
            end_of_observation_utc = None
            simulation_end = self._as_utc(contest.end_date)
            eval_n_steps = None

        # ── Resume support ────────────────────────────────────────────
        # Start sequence_id from the last committed observation so that a
        # resumed session continues rather than restarting numbering from zero.
        async with db_factory() as db:
            max_seq_result = await db.execute(
                select(func.max(SensorObservation.sequence_id)).where(
                    SensorObservation.session_id == session.id
                )
            )
        sequence_id = max_seq_result.scalar() or 0
        committed_through = sequence_id

        paused = False          # set True when PAUSED status detected
        in_evaluation = False   # set True after end_of_observation is crossed
        should_store = False    # set per step inside the loop; False if the loop
                                # never runs (e.g. simulation_end already past)

        # Absolute tick scheduling: each step is anchored to next_tick so that
        # per-step computation time does not accumulate as wall-clock drift.
        event_loop = asyncio.get_running_loop()
        next_tick = event_loop.time() + dt

        async with db_factory() as db:

            while (
                simulation_end is not None
                and datetime.now(timezone.utc) < simulation_end
            ):
                sequence_id += 1

                # ── Phase transition check (two-phase contests only) ──
                if two_phase and not in_evaluation:
                    now = datetime.now(timezone.utc)
                    if now >= end_of_observation_utc:
                        in_evaluation = True
                        # Notify all connected participants that the stream
                        # is ending and the evaluation window is starting.
                        await self._broadcast(
                            str(session.contest_id),
                            {
                                "event": "evaluation_started",
                                "observation_end_sequence_id": sequence_id - 1,
                                "evaluation_steps": eval_n_steps,
                            },
                        )

                loop = asyncio.get_running_loop()
                new_state = await loop.run_in_executor(
                    None,
                    lambda s=state: self._call_plugin(
                        twin.twin_id, "step", twin.step, s, dt
                    ),
                )

                sensors = {}
                ground_truth = {}
                for sensor in contest_sensors:
                    sensors[sensor.sensor_id] = self._call_plugin(
                        sensor.sensor_id, "observe", sensor.observe, new_state, dt
                    )
                    # Clean latent-state value — no noise, drift, or outliers.
                    raw = new_state.get_quantity(sensor.measured_quantity)
                    if raw is not None:
                        ground_truth[sensor.sensor_id] = float(raw)

                active_faults = twin.get_active_faults()
                labels = {
                    "is_anomaly": len(active_faults) > 0,
                    "fault_ids": [fault["fault_id"] for fault in active_faults],
                    "severities": {
                        fault["fault_id"]: fault["severity"]
                        for fault in active_faults
                    },
                }

                timestamp = datetime.now(timezone.utc)

                # ── Store only during the evaluation phase ────────────
                should_store = (not two_phase) or in_evaluation
                if should_store:
                    observation = SensorObservation(
                        session_id=session.id,
                        sequence_id=sequence_id,
                        timestamp=timestamp,
                        sensors=sensors,
                        ground_truth=ground_truth or None,
                        labels=labels,
                    )
                    db.add(observation)

                if sequence_id % commit_interval == 0:
                    if should_store:
                        await db.commit()
                        committed_through = sequence_id
                    async with db_factory() as refresh_db:
                        refreshed = await self._load_contest(
                            refresh_db, session.contest_id
                        )
                    if not two_phase:
                        # Classic mode: respect dynamic end_date updates.
                        simulation_end = self._as_utc(refreshed.end_date)
                    if refreshed.status == "PAUSED":
                        paused = True
                        break
                    if refreshed.status == "CLOSED":
                        # Notify connected clients so their WebSocket closes cleanly.
                        await self._broadcast(
                            str(session.contest_id),
                            {"event": "contest_closed"},
                        )
                        break

                # ── Broadcast only during the observation phase ───────
                should_broadcast = (not two_phase) or (not in_evaluation)
                if should_broadcast:
                    await self._broadcast(
                        str(session.contest_id),
                        {
                            "timestamp": timestamp.isoformat(),
                            "session_id": str(session.id),
                            "sequence_id": sequence_id,
                            "committed_through": committed_through,
                            "sensors": sensors,
                        },
                    )

                state = new_state
                # Sleep until the next absolute tick. If a step overran its
                # slot, skip ahead without sleeping instead of accumulating
                # the delay into every subsequent step.
                now_monotonic = event_loop.time()
                delay = next_tick - now_monotonic
                if delay > 0:
                    await asyncio.sleep(delay)
                    next_tick += dt
                else:
                    next_tick = now_monotonic + dt

            if not paused and should_store:
                await db.commit()
                committed_through = sequence_id

        async with db_factory() as db:
            session = await self._load_session(db, str(session.id))
            session.status = "PAUSED" if paused else "COMPLETED"
            session.ended_at = datetime.now(timezone.utc)
            await db.commit()

        if not paused and two_phase:
            await self._notify_submission_window_open(db_factory, session)

    def _call_plugin(self, plugin_id: str, method_name: str, method, *args):
        try:
            return method(*args)
        except PluginExecutionError:
            raise
        except Exception as exc:
            raise PluginExecutionError(
                f"plugin '{plugin_id}' raised an error in {method_name}()"
            ) from exc

    async def _load_contest(self, db, contest_id: UUID) -> Contest:
        result = await db.execute(select(Contest).where(Contest.id == contest_id))
        contest = result.scalar_one_or_none()
        if contest is None:
            raise PluginExecutionError(f"contest '{contest_id}' does not exist")
        return contest

    def _build_configured_sensor(
        self, config: dict, twin, supported_quantities, rng: random.Random | None = None
    ):
        sensor_id = config.get("sensor_id")
        if not sensor_id:
            raise PluginExecutionError("sensor config is missing sensor_id")

        try:
            registered_sensor = registry_module.sensor_registry.get(sensor_id)
        except PluginNotFoundError as exc:
            raise PluginExecutionError(
                f"sensor '{sensor_id}' could not be loaded"
            ) from exc

        if registered_sensor.measured_quantity not in supported_quantities:
            raise PluginExecutionError(
                f"sensor '{sensor_id}' is not compatible with twin '{twin.twin_id}'"
            )

        overrides = {
            key: value
            for key, value in config.items()
            if key not in ("sensor_id", "rng")  # rng is never user-configurable
        }

        # Configuration goes through the Sensor.configure() contract; the
        # default implementation reconstructs the sensor from its class and
        # injects the per-session RNG when the constructor supports it.
        try:
            configured_sensor = registered_sensor.configure(overrides, rng)
        except TypeError as exc:
            raise PluginExecutionError(
                f"sensor '{sensor_id}' could not be configured"
            ) from exc

        return configured_sensor

    async def _broadcast(self, contest_id: str, payload: dict) -> None:
        if self._broadcaster:
            await self._broadcaster.broadcast(contest_id, payload)

    async def _notify_session_failed(
        self, db_factory, session: SimulationSession, error: str
    ) -> None:
        """Alert the contest owner and all administrators. Best-effort."""
        if self._notifications is None:
            return
        try:
            async with db_factory() as db:
                contest_result = await db.execute(
                    select(Contest).where(Contest.id == session.contest_id)
                )
                contest = contest_result.scalar_one_or_none()
                contest_name = contest.name if contest else str(session.contest_id)
                recipients: dict[str, None] = {}
                if contest is not None and contest.created_by is not None:
                    owner_result = await db.execute(
                        select(User).where(User.id == contest.created_by)
                    )
                    owner = owner_result.scalar_one_or_none()
                    if owner is not None:
                        recipients[owner.email] = None
                admins_result = await db.execute(
                    select(User).where(
                        User.role == "ADMINISTRATOR", User.status == "ACTIVE"
                    )
                )
                for admin in admins_result.scalars():
                    recipients[admin.email] = None
            for email in recipients:
                await self._notifications.notify(SessionFailed(
                    to_email=email,
                    contest_name=contest_name,
                    error=error,
                ))
        except Exception:
            # Notifications are best-effort; never mask the original failure.
            pass

    async def _notify_submission_window_open(
        self, db_factory, session: SimulationSession
    ) -> None:
        """Tell every registered participant that submissions are open."""
        if self._notifications is None:
            return
        try:
            async with db_factory() as db:
                contest_result = await db.execute(
                    select(Contest).where(Contest.id == session.contest_id)
                )
                contest = contest_result.scalar_one_or_none()
                if contest is None:
                    return
                participants_result = await db.execute(
                    select(User)
                    .join(ContestRegistration, ContestRegistration.user_id == User.id)
                    .where(
                        ContestRegistration.contest_id == contest.id,
                        ContestRegistration.status == "REGISTERED",
                        User.status == "ACTIVE",
                    )
                )
                emails = [user.email for user in participants_result.scalars()]
                contest_name = contest.name
            for email in emails:
                await self._notifications.notify(SubmissionWindowOpen(
                    to_email=email,
                    contest_name=contest_name,
                ))
        except Exception:
            pass

    def _as_utc(self, value):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
