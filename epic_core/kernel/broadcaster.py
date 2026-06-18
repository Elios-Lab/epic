"""Contest WebSocket broadcast fan-out."""

from __future__ import annotations

import asyncio
import threading
import time


class ContestBroadcaster:
    """
    Fan-out broadcaster for contest simulation streams.
    One instance lives on app.state, shared between the engine
    and the WebSocket handler.
    """

    def __init__(self, queue_capacity: int = 1000) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._capacity = queue_capacity
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, contest_id: str) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=self._capacity)
        self._subscribers.setdefault(contest_id, set()).add(queue)
        return queue

    def unsubscribe(self, contest_id: str, queue: asyncio.Queue) -> None:
        subscribers = self._subscribers.get(contest_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(contest_id, None)

    def _put_to_queues(self, contest_id: str, payload: dict) -> None:
        """Put payload onto each subscriber queue. Must run on the broadcaster's event loop."""
        for queue in list(self._subscribers.get(contest_id, set())):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(payload)

    async def broadcast(self, contest_id: str, payload: dict) -> None:
        self._put_to_queues(contest_id, payload)

    def broadcast_sync(self, contest_id: str, payload: dict, timeout: float = 5.0) -> None:
        """Thread-safe broadcast from a synchronous (non-async) context.

        Waits until at least one subscriber is registered (the WebSocket handler
        may not have called subscribe() yet when the test calls this), then
        schedules the put on the broadcaster's event loop via call_soon_threadsafe
        so that asyncio.Queue waiters are woken up correctly. Blocks until delivered.
        Requires set_loop() to have been called at app startup.
        """
        if self._loop is None:
            raise RuntimeError("ContestBroadcaster.set_loop() must be called before broadcast_sync()")

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.subscriber_count(contest_id) > 0:
                break
            time.sleep(0.005)

        done = threading.Event()

        def _do() -> None:
            self._put_to_queues(contest_id, payload)
            done.set()

        self._loop.call_soon_threadsafe(_do)
        done.wait(timeout=timeout)

    def subscriber_count(self, contest_id: str) -> int:
        return len(self._subscribers.get(contest_id, set()))
