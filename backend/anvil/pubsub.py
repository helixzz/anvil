from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from typing import Any


class Broadcaster:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[Any]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str) -> asyncio.Queue[Any]:
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=256)
        async with self._lock:
            self._subscribers[topic].add(queue)
        return queue

    async def unsubscribe(self, topic: str, queue: asyncio.Queue[Any]) -> None:
        async with self._lock:
            self._subscribers[topic].discard(queue)
            if not self._subscribers[topic]:
                self._subscribers.pop(topic, None)

    async def publish(self, topic: str, message: Any) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(topic, ()))
        for q in queues:
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(message)


_instance: Broadcaster | None = None


def get_broadcaster() -> Broadcaster:
    global _instance
    if _instance is None:
        _instance = Broadcaster()
    return _instance
