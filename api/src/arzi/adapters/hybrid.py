"""Hybrid mode: recorded answers for the demo cases, live Gemini for everything else.

The live link must be instant and free for the three demo cases, yet must not fail on a
visitor's own document. A recording miss (and only a miss) falls through to the live client,
which sits behind the daily budget guard; any other error is returned as it is.
"""

from typing import Any

from pydantic import BaseModel

from arzi.services.ports import LlmRequest, LlmResult, LlmUnavailableError, SpeechResult

REPLAY_MISS = "replay-miss"


class ReplayThenLiveLlm:
    def __init__(self, replay: Any, live: Any) -> None:  # noqa: ANN401 - any LlmClient
        self._replay = replay
        self._live = live

    async def generate_structured[T: BaseModel](self, request: LlmRequest[T]) -> LlmResult[T]:
        try:
            result: LlmResult[T] = await self._replay.generate_structured(request)
        except LlmUnavailableError as error:
            if error.slug != REPLAY_MISS:
                raise
            result = await self._live.generate_structured(request)
        return result


class ReplayThenLiveSpeech:
    def __init__(self, replay: Any, live: Any) -> None:  # noqa: ANN401 - any SpeechClient
        self._replay = replay
        self._live = live

    async def synthesize(self, text: str, lang: str) -> SpeechResult:
        try:
            result: SpeechResult = await self._replay.synthesize(text, lang)
        except LlmUnavailableError as error:
            if error.slug != REPLAY_MISS:
                raise
            result = await self._live.synthesize(text, lang)
        return result
