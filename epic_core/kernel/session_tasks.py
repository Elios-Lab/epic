"""In-memory registry for live simulation session tasks.

The registry is intentionally process-local: it coordinates background
simulation tasks inside one FastAPI/Uvicorn process. A distributed scheduler
is required before running simulations across multiple API worker processes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from epic_core.kernel.exceptions import ContestStateError


@dataclass
class _SessionTaskEntry:
    contest_id: str
    session_id: str
    task: asyncio.Task | None = None


class SessionTaskRegistry:
    def __init__(self, max_sessions: int) -> None:
        self.max_sessions = max_sessions
        self._entries: dict[str, _SessionTaskEntry] = {}
        self._lock = asyncio.Lock()

    async def reserve(self, contest_id: str, session_id: str) -> None:
        async with self._lock:
            self._prune_done_locked()
            if contest_id in self._entries:
                raise ContestStateError(
                    "A simulation runner is already active for this contest"
                )
            if len(self._entries) >= self.max_sessions:
                raise ContestStateError(
                    "Maximum number of concurrent simulation sessions reached"
                )
            self._entries[contest_id] = _SessionTaskEntry(
                contest_id=contest_id,
                session_id=session_id,
            )

    async def attach(self, contest_id: str, task: asyncio.Task) -> None:
        async with self._lock:
            entry = self._entries.get(contest_id)
            if entry is None:
                raise ContestStateError(
                    "No simulation runner reservation exists for this contest"
                )
            entry.task = task
        task.add_done_callback(
            lambda completed: self._drop_completed(contest_id, completed)
        )

    async def release(self, contest_id: str, session_id: str | None = None) -> None:
        async with self._lock:
            entry = self._entries.get(contest_id)
            if entry is None:
                return
            if session_id is not None and entry.session_id != session_id:
                return
            self._entries.pop(contest_id, None)

    async def wait_until_clear(self, contest_id: str, timeout: float) -> bool:
        async with self._lock:
            self._prune_done_locked()
            entry = self._entries.get(contest_id)
            task = entry.task if entry is not None else None

        if task is None:
            return entry is None

        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except asyncio.TimeoutError:
            return False
        except asyncio.CancelledError:
            return True

        async with self._lock:
            self._prune_done_locked()
            return contest_id not in self._entries

    async def cancel_all(self) -> None:
        async with self._lock:
            tasks = [
                entry.task
                for entry in self._entries.values()
                if entry.task is not None and not entry.task.done()
            ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        async with self._lock:
            self._entries.clear()

    def active_count(self) -> int:
        self._prune_done_locked()
        return len(self._entries)

    def _drop_completed(self, contest_id: str, completed: asyncio.Task) -> None:
        if not completed.cancelled():
            completed.exception()
        entry = self._entries.get(contest_id)
        if entry is not None and entry.task is completed:
            self._entries.pop(contest_id, None)

    def _prune_done_locked(self) -> None:
        done_contests = [
            contest_id
            for contest_id, entry in self._entries.items()
            if entry.task is not None and entry.task.done()
        ]
        for contest_id in done_contests:
            self._entries.pop(contest_id, None)
