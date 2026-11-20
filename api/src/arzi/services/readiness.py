"""Readiness: can this instance reach the backing services it needs to serve traffic?

Probes run concurrently under one timeout so a hung dependency cannot stall the endpoint
beyond what Cloud Run's startup and liveness checks tolerate.
"""

import time
from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

import anyio
from pydantic import BaseModel, ConfigDict


class ReadinessProbe(Protocol):
    """A cheap, read-only reachability check against one dependency."""

    @property
    def name(self) -> str: ...

    async def check(self) -> None:
        """Return normally when reachable; raise on any failure."""
        ...


class CheckState(StrEnum):
    OK = "ok"
    FAILED = "failed"


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    state: CheckState
    latency_ms: int
    detail: str | None = None


class ReadinessReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    ready: bool
    checks: tuple[CheckResult, ...]


async def _run_probe(probe: ReadinessProbe, timeout_s: float) -> CheckResult:
    started = time.perf_counter()
    detail: str | None
    try:
        with anyio.fail_after(timeout_s):
            await probe.check()
    except TimeoutError:
        state, detail = CheckState.FAILED, "timeout"
    except Exception as exc:
        # Only the exception type is reported: messages from cloud SDKs can carry resource
        # names or request payloads we do not want in a public response.
        state, detail = CheckState.FAILED, type(exc).__name__
    else:
        state, detail = CheckState.OK, None
    latency_ms = round((time.perf_counter() - started) * 1000)
    return CheckResult(name=probe.name, state=state, latency_ms=latency_ms, detail=detail)


async def check_readiness(probes: Sequence[ReadinessProbe], timeout_s: float) -> ReadinessReport:
    """Run every probe concurrently; the instance is ready only if all of them pass."""
    results: list[CheckResult | None] = [None] * len(probes)

    async def run(index: int, probe: ReadinessProbe) -> None:
        results[index] = await _run_probe(probe, timeout_s)

    async with anyio.create_task_group() as tg:
        for index, probe in enumerate(probes):
            tg.start_soon(run, index, probe)

    checks = tuple(r for r in results if r is not None)
    return ReadinessReport(ready=all(c.state is CheckState.OK for c in checks), checks=checks)
