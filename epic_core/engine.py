"""Domain-independent simulation engine."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from uuid import UUID

import numpy as np
from sqlalchemy import select

import epic_core.registry as registry_module
from epic_core.broadcaster import ContestBroadcaster
from epic_core.db.models import Contest, SensorObservation, SimulationSession
from epic_core.exceptions import PluginExecutionError, PluginNotFoundError
from epic_core.interfaces import SensorFault


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
                await self._run_loop(session, db)
            except Exception as exc:
                session.status = "FAILED"
                session.session_metadata = {
                    **(session.session_metadata or {}),
                    "error": str(exc),
                }
                session.ended_at = datetime.now(timezone.utc)
                await db.commit()
                return

    async def _load_session(self, db, session_id: str) -> SimulationSession:
        result = await db.execute(
            select(SimulationSession).where(SimulationSession.id == UUID(session_id))
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise PluginExecutionError(f"session '{session_id}' does not exist")
        return session

    async def _run_loop(self, session: SimulationSession, db) -> None:
        contest = await self._load_contest(db, session.contest_id)
        try:
            twin = registry_module.twin_registry.get(session.twin_id)
        except PluginNotFoundError as exc:
            raise PluginExecutionError(
                f"twin '{session.twin_id}' could not be loaded"
            ) from exc

        try:
            scenario = next(
                candidate
                for candidate in twin.get_scenarios()
                if candidate.scenario_id == session.scenario_id
            )
        except StopIteration as exc:
            raise PluginExecutionError(
                f"scenario '{session.scenario_id}' could not be loaded"
            ) from PluginNotFoundError(session.scenario_id)

        config = self._call_plugin(
            scenario.scenario_id, "initialize", scenario.initialize
        )
        state = self._call_plugin(
            twin.twin_id,
            "create_initial_state",
            twin.create_initial_state,
            config.get("initial_conditions"),
        )
        scheduled_faults = []
        for entry in self._call_plugin(
            scenario.scenario_id,
            "get_fault_schedule",
            scenario.get_fault_schedule,
        ):
            try:
                fault = registry_module.fault_registry.get(entry["fault_id"])
            except PluginNotFoundError as exc:
                raise PluginExecutionError(
                    f"fault '{entry['fault_id']}' could not be loaded"
                ) from exc
            scheduled_faults.append((entry, fault))

        if session.seed is not None:
            random.seed(session.seed)
            np.random.seed(session.seed)

        active_faults: set = set()
        dt = 1.0 / session.sampling_rate_hz
        t = 0.0
        sequence_id = 0
        commit_interval = 100
        contest_end_date = self._as_utc(contest.end_date)

        while (
            contest_end_date is not None
            and datetime.now(timezone.utc) < contest_end_date
        ):
            t += dt
            sequence_id += 1

            for entry, fault in scheduled_faults:
                if t >= entry["start_time"] and fault not in active_faults:
                    self._call_plugin(
                        fault.fault_id, "activate", fault.activate, entry["severity"]
                    )
                    active_faults.add(fault)
                if (
                    entry["end_time"] is not None
                    and t >= entry["end_time"]
                    and fault in active_faults
                ):
                    self._call_plugin(fault.fault_id, "deactivate", fault.deactivate)
                    active_faults.remove(fault)

            new_state = self._call_plugin(twin.twin_id, "step", twin.step, state, dt)
            for fault in list(active_faults):
                if not isinstance(fault, SensorFault):
                    self._call_plugin(
                        fault.fault_id, "apply", fault.apply, new_state, dt
                    )

            sensors = {}
            for sensor in twin.get_sensors():
                raw = self._call_plugin(
                    sensor.sensor_id, "observe", sensor.observe, new_state
                )
                for fault in active_faults:
                    if isinstance(fault, SensorFault) and (
                        not fault.target_sensor_ids
                        or sensor.sensor_id in fault.target_sensor_ids
                    ):
                        raw = self._call_plugin(
                            fault.fault_id,
                            "apply_to_measurement",
                            fault.apply_to_measurement,
                            raw,
                        )
                sensors[sensor.sensor_id] = raw

            labels = {
                "is_anomaly": len(active_faults) > 0,
                "fault_ids": [fault.fault_id for fault in active_faults],
                "severities": {
                    fault.fault_id: fault.current_severity
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
            await asyncio.sleep(dt)

        await db.commit()
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

    async def _broadcast(self, contest_id: str, payload: dict) -> None:
        if self._broadcaster:
            await self._broadcaster.broadcast(contest_id, payload)

    def _as_utc(self, value):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
