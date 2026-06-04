"""Domain-independent simulation engine."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import numpy as np
from sqlalchemy import select

import epic_core.registry as registry_module
from epic_core.db.models import SensorObservation, SimulationSession
from epic_core.exceptions import PluginExecutionError, PluginNotFoundError
from epic_core.interfaces import SensorFault


class SimulationEngine:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._db_factories: dict[str, Any] = {}

    async def run_session(self, session_id: str, db_factory) -> None:
        current_task = asyncio.current_task()
        if current_task is not None:
            self._tasks[session_id] = current_task
            self._db_factories[session_id] = db_factory

        try:
            async with db_factory() as db:
                session = await self._load_session(db, session_id)
                session.status = "RUNNING"
                session.started_at = datetime.now(timezone.utc)
                await db.commit()

                try:
                    await self._run_loop(session, db, db_factory)
                except asyncio.CancelledError:
                    session.status = "CANCELLED"
                    session.ended_at = datetime.now(timezone.utc)
                    await db.commit()
                    raise
                except Exception as exc:
                    session.status = "FAILED"
                    session.session_metadata = {
                        **(session.session_metadata or {}),
                        "error": str(exc),
                    }
                    session.ended_at = datetime.now(timezone.utc)
                    await db.commit()
                    return
        finally:
            self._tasks.pop(session_id, None)
            self._db_factories.pop(session_id, None)

    def cancel_session(self, session_id: str) -> None:
        task = self._tasks.get(session_id)
        if task is not None:
            task.cancel()
        db_factory = self._db_factories.get(session_id)
        if db_factory is not None:
            asyncio.create_task(self._mark_cancelled(session_id, db_factory))

    async def _mark_cancelled(self, session_id: str, db_factory) -> None:
        async with db_factory() as db:
            session = await self._load_session(db, session_id)
            session.status = "CANCELLED"
            session.ended_at = datetime.now(timezone.utc)
            await db.commit()

    async def _load_session(self, db, session_id: str) -> SimulationSession:
        result = await db.execute(
            select(SimulationSession).where(SimulationSession.id == UUID(session_id))
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise PluginExecutionError(f"session '{session_id}' does not exist")
        return session

    async def _run_loop(self, session: SimulationSession, db, db_factory) -> None:
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

        while t < session.duration_seconds - 1e-12:
            t += dt
            sequence_id += 1

            for entry, fault in scheduled_faults:
                if t >= entry["start_time"] and fault not in active_faults:
                    self._call_plugin(fault.fault_id, "activate", fault.activate, entry["severity"])
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
                    self._call_plugin(fault.fault_id, "apply", fault.apply, new_state, dt)

            sensors = {}
            for sensor in twin.get_sensors():
                raw = self._call_plugin(sensor.sensor_id, "observe", sensor.observe, new_state)
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

            labels = None
            if session.mode == "TRAINING":
                labels = {
                    "is_anomaly": len(active_faults) > 0,
                    "fault_ids": [fault.fault_id for fault in active_faults],
                    "severities": {
                        fault.fault_id: fault.current_severity
                        for fault in active_faults
                    },
                }

            db.add(
                SensorObservation(
                    session_id=session.id,
                    sequence_id=sequence_id,
                    timestamp=datetime.now(timezone.utc),
                    sensors=sensors,
                    labels=labels,
                )
            )
            state = new_state

            if sequence_id % commit_interval == 0:
                await db.commit()
            await asyncio.sleep(0)

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

