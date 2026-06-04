"""Contest WebSocket broadcast fan-out."""

from __future__ import annotations

import asyncio


class ContestBroadcaster:
    """
    Fan-out broadcaster for contest simulation streams.
    One instance lives on app.state, shared between the engine
    and the WebSocket handler.
    """

    def __init__(self, queue_capacity: int = 1000) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._capacity = queue_capacity

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

    async def broadcast(self, contest_id: str, payload: dict) -> None:
        for queue in list(self._subscribers.get(contest_id, set())):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(payload)

    def subscriber_count(self, contest_id: str) -> int:
        return len(self._subscribers.get(contest_id, set()))

