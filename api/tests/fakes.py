"""In-memory fakes for ports, shared by unit and integration tests."""

import anyio


class FakeProbe:
    """Readiness probe whose outcome is scripted: pass, raise, or hang past the timeout."""

    def __init__(self, name: str, *, error: Exception | None = None, delay_s: float = 0.0) -> None:
        self.name = name
        self._error = error
        self._delay_s = delay_s
        self.calls = 0

    async def check(self) -> None:
        self.calls += 1
        if self._delay_s:
            await anyio.sleep(self._delay_s)
        if self._error is not None:
            raise self._error
