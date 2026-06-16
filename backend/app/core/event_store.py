"""
In-memory ring buffer for the most recent AnalysisResult objects.

Used by the polling endpoint so clients can fetch the latest events without
a persistent WebSocket connection.
"""

from collections import deque
from functools import lru_cache

from app.models import AnalysisResult


class EventStore:
    def __init__(self, maxlen: int = 50) -> None:
        self._store: deque[AnalysisResult] = deque(maxlen=maxlen)

    def append(self, result: AnalysisResult) -> None:
        self._store.append(result)

    def latest(self, n: int = 5) -> list[AnalysisResult]:
        """Return the n most recent results, newest first."""
        items = list(self._store)
        tail = items[-n:] if len(items) > n else items
        return list(reversed(tail))

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


@lru_cache(maxsize=1)
def get_event_store() -> EventStore:
    return EventStore()
