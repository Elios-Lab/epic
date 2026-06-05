"""Domain-independent simulation engine."""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone
from uuid import UUID

import numpy as np
from sqlalchemy import select

import epic_core.registry as registry_module
from epic_core.broadcaster import ContestBroadcaster
from epic_core.db.models import Contest, SensorObservation, SimulationSession
from epic_core.exceptions import PluginExecutionError, PluginNotFoundError


class SimulationEngine:
    def __init__(self, broadcaster: ContestBroadcaster | None = None) -> None:
        self._broadcaster = broadcaster

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

        supported = twin.supported_quantities()
        contest_sensors = []
        for cfg in contest.sensor_configs:
            contest_sensors.append(self._build_configured_sensor(cfg, twin, supported))

        available_faults = {fault.fault_id for fault in twin.get_faults()}
        for entry in contest.fault_schedule:
            fault_id = entry.get("fault_id")
            if fault_id not in available_faults:
                raise PluginExecutionError(
                    f"fault '{fault_id}' is not available for twin '{twin.twin_id}'"
                )

        if session.seed is not None:
            import random

            random.seed(session.seed)
            np.random.seed(session.seed)

        state = self._call_plugin(
            twin.twin_id,
            "configure",
            twin.configure,
            contest.initial_conditions,
            contest.fault_schedule,
        )

        dt = 1.0 / session.sampling_rate_hz
        sequence_id = 0
        commit_interval = 100

        async with db_factory() as db:
            contest_end_date = self._as_utc(contest.end_date)

            while (
                contest_end_date is not None
                and datetime.now(timezone.utc) < contest_end_date
            ):
                sequence_id += 1

                loop = asyncio.get_running_loop()
                new_state = await loop.run_in_executor(
                    None,
                    lambda s=state: self._call_plugin(
                        twin.twin_id, "step", twin.step, s, dt
                    ),
                )

                sensors = {}
                for sensor in contest_sensors:
                    sensors[sensor.sensor_id] = self._call_plugin(
                        sensor.sensor_id, "observe", sensor.observe, new_state, dt
                    )

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
                observation = SensorObservation(
                    session_id=session.id,
                    sequence_id=sequence_id,
                    timestamp=timestamp,
                    sensors=sensors,
                    labels=labels,
                )
                db.add(observation)
                await self._broadcast(
                    str(session.contest_id),
                    {
                        "timestamp": timestamp.isoformat(),
                        "session_id": str(session.id),
                        "sequence_id": sequence_id,
                        "sensors": sensors,
                    },
                )
                state = new_state

                if sequence_id % commit_interval == 0:
                    await db.commit()
                    async with db_factory() as refresh_db:
                        refreshed = await self._load_contest(
                            refresh_db, session.contest_id
                        )
                    contest_end_date = self._as_utc(refreshed.end_date)

                await asyncio.sleep(dt)

            await db.commit()

        async with db_factory() as db:
            session = await self._load_session(db, str(session.id))
            session.status = "COMPLETED"
            session.ended_at = datetime.now(timezone.utc)
            await db.commit()

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

    def _build_configured_sensor(self, config: dict, twin, supported_quantities):
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

        overrides = {key: value for key, value in config.items() if key != "sensor_id"}
        sensor_class = registered_sensor.__class__
        try:
            configured_sensor = sensor_class(**overrides)
        except TypeError as exc:
            raise PluginExecutionError(
                f"sensor '{sensor_id}' could not be configured"
            ) from exc

        return configured_sensor

    async def _broadcast(self, contest_id: str, payload: dict) -> None:
        if self._broadcaster:
            await self._broadcaster.broadcast(contest_id, payload)

    def _as_utc(self, value):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
