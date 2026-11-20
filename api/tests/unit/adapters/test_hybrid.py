"""Hybrid mode falls through to the live client on a recording miss, and only then."""

from typing import Any

import pytest

from arzi.adapters.hybrid import ReplayThenLiveLlm, ReplayThenLiveSpeech
from arzi.services.ports import LlmUnavailableError


class _Client:
    def __init__(self, error: str | None = None) -> None:
        self.error, self.calls = error, 0

    async def generate_structured(self, request: Any) -> str:  # noqa: ANN401
        return await self._answer("llm")

    async def synthesize(self, text: str, lang: str) -> str:
        return await self._answer("speech")

    async def _answer(self, value: str) -> str:
        self.calls += 1
        if self.error:
            raise LlmUnavailableError(self.error)
        return value


def _llm(replay: Any, live: Any) -> Any:  # noqa: ANN401
    return ReplayThenLiveLlm(replay, live)


def _speech(replay: Any, live: Any) -> Any:  # noqa: ANN401
    return ReplayThenLiveSpeech(replay, live)


async def test_a_recording_is_served_without_a_live_call() -> None:
    replay, live = _Client(), _Client()
    assert await _llm(replay, live).generate_structured(object()) == "llm"
    assert (replay.calls, live.calls) == (1, 0)


async def test_a_miss_goes_live_for_text_and_speech() -> None:
    llm_live, speech_live = _Client(), _Client()
    assert await _llm(_Client("replay-miss"), llm_live).generate_structured(object()) == "llm"
    assert await _speech(_Client("replay-miss"), speech_live).synthesize("a", "en") == "speech"
    assert (llm_live.calls, speech_live.calls) == (1, 1)


async def test_other_failures_do_not_trigger_a_live_call() -> None:
    live = _Client()
    with pytest.raises(LlmUnavailableError):
        await _llm(_Client("budget-reached"), live).generate_structured(object())
    assert live.calls == 0
