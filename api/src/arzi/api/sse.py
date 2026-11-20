"""Server-sent events with heartbeats.

Each run event goes out with its ``seq`` as the SSE id, so a browser that reconnects sends
``Last-Event-ID`` and resumes where it left off. A comment line every few seconds keeps proxies
from closing an idle stream while a long extraction runs.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator

from arzi.domain.models import RunEvent

_DONE = object()


def format_event(event: RunEvent) -> str:
    payload = event.model_dump_json(exclude={"seq", "type"})
    return f"id: {event.seq}\nevent: {event.type}\ndata: {payload}\n\n"


async def stream(events: AsyncIterator[RunEvent], heartbeat_s: float) -> AsyncIterator[str]:
    queue: asyncio.Queue[object] = asyncio.Queue()

    async def pump() -> None:
        try:
            async for event in events:
                await queue.put(event)
        finally:
            await queue.put(_DONE)

    task = asyncio.create_task(pump())
    try:
        yield "retry: 3000\n\n"
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if item is _DONE:
                return
            assert isinstance(item, RunEvent)  # noqa: S101 - only events and the sentinel are queued
            yield format_event(item)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
