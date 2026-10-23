"""Job worker loop.

Phase 0 placeholder: it only idles. F3 replaces the body of `_drain` with job claiming.

The idle strategy is fixed now (overview §5): wait on an in-process wake event, with a
long timeout, instead of polling the database every few seconds. Polling would keep the
Neon compute awake and burn the free plan's compute hours.
"""

import asyncio

from app.core.logging import get_logger

log = get_logger(__name__)

DEFAULT_HEARTBEAT_SECONDS = 3600


class Worker:
    def __init__(self, *, heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS) -> None:
        self._heartbeat_seconds = heartbeat_seconds
        self._wake_event = asyncio.Event()
        self.wakeups = 0

    def wake(self) -> None:
        """Called by the API after committing a new job (same process, ROLE=all)."""
        self._wake_event.set()

    async def run(self) -> None:
        log.info("worker_started")
        while True:
            try:
                async with asyncio.timeout(self._heartbeat_seconds):
                    await self._wake_event.wait()
            except TimeoutError:
                log.info("worker_heartbeat")
                continue
            self._wake_event.clear()
            self.wakeups += 1
            await self._drain()

    async def _drain(self) -> None:
        """Process every claimable job. Nothing to claim until F3."""
