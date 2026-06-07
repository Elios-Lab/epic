"""Tests for ContestBroadcaster."""

import asyncio

import pytest

from epic_core.broadcaster import ContestBroadcaster


@pytest.fixture
def broadcaster():
    return ContestBroadcaster(queue_capacity=3)


@pytest.mark.asyncio
async def test_subscriber_receives_broadcast(broadcaster):
    queue = broadcaster.subscribe("contest_1")

    await broadcaster.broadcast("contest_1", {"tick": 1})

    assert not queue.empty()
    assert queue.get_nowait() == {"tick": 1}


@pytest.mark.asyncio
async def test_multiple_subscribers_all_receive_message(broadcaster):
    q1 = broadcaster.subscribe("contest_1")
    q2 = broadcaster.subscribe("contest_1")

    await broadcaster.broadcast("contest_1", {"tick": 1})

    assert q1.get_nowait() == {"tick": 1}
    assert q2.get_nowait() == {"tick": 1}


@pytest.mark.asyncio
async def test_broadcast_to_unknown_contest_does_not_raise(broadcaster):
    # No subscribers for "contest_x" — must not raise
    await broadcaster.broadcast("contest_x", {"tick": 1})


@pytest.mark.asyncio
async def test_full_queue_drops_oldest_and_accepts_new_message(broadcaster):
    # queue_capacity=3; fill it completely
    queue = broadcaster.subscribe("contest_1")
    for i in range(3):
        await broadcaster.broadcast("contest_1", {"tick": i})

    assert queue.full()

    # Broadcasting one more should drop the oldest (tick=0) and add tick=3
    await broadcaster.broadcast("contest_1", {"tick": 3})

    assert queue.full()
    messages = [queue.get_nowait() for _ in range(3)]
    assert messages == [{"tick": 1}, {"tick": 2}, {"tick": 3}]


@pytest.mark.asyncio
async def test_full_queue_broadcast_does_not_raise(broadcaster):
    queue = broadcaster.subscribe("contest_1")
    # Fill to capacity
    for i in range(3):
        await broadcaster.broadcast("contest_1", {"tick": i})

    # Simulate a concurrent consumer draining the queue between full() and get_nowait()
    # by draining manually before the next broadcast — the try/except must handle this.
    while not queue.empty():
        queue.get_nowait()

    # Broadcasting to a now-empty queue that was full() at check time must not raise
    await broadcaster.broadcast("contest_1", {"tick": 99})

    assert queue.get_nowait() == {"tick": 99}


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue(broadcaster):
    queue = broadcaster.subscribe("contest_1")
    assert broadcaster.subscriber_count("contest_1") == 1

    broadcaster.unsubscribe("contest_1", queue)

    assert broadcaster.subscriber_count("contest_1") == 0


@pytest.mark.asyncio
async def test_unsubscribed_queue_receives_no_further_messages(broadcaster):
    queue = broadcaster.subscribe("contest_1")
    broadcaster.unsubscribe("contest_1", queue)

    await broadcaster.broadcast("contest_1", {"tick": 1})

    assert queue.empty()


@pytest.mark.asyncio
async def test_unsubscribe_unknown_contest_does_not_raise(broadcaster):
    queue = asyncio.Queue()
    broadcaster.unsubscribe("nonexistent", queue)


@pytest.mark.asyncio
async def test_subscriber_count_is_zero_after_last_unsubscribe(broadcaster):
    q1 = broadcaster.subscribe("c")
    q2 = broadcaster.subscribe("c")
    broadcaster.unsubscribe("c", q1)
    broadcaster.unsubscribe("c", q2)

    assert broadcaster.subscriber_count("c") == 0
    # Internal dict entry should be cleaned up
    assert "c" not in broadcaster._subscribers
