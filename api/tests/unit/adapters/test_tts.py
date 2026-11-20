"""Narration adapters: Gemini TTS (faked), MP3 encoding, budget guard, record and replay."""

import datetime as dt
import io
import wave
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors

from arzi.adapters.memory import InMemoryCostLedger
from arzi.adapters.tts import (
    BudgetedSpeech,
    GeminiSpeech,
    RecordingSpeech,
    ReplaySpeech,
    SilentSpeech,
    as_wav,
    wav_to_mp3,
)
from arzi.services.cost_ledger import BudgetExceededError, ModelPrice, PriceUnknownError
from arzi.services.ports import LlmUnavailableError

T0 = dt.datetime(2026, 11, 20, 9, 0, tzinfo=dt.UTC)


def _wav(seconds: float = 1.0, rate: int = 24_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(bytes(int(rate * seconds) * 2))
    return buffer.getvalue()


def _response(data: bytes, mime_type: str = "audio/wav") -> SimpleNamespace:
    part = SimpleNamespace(inline_data=SimpleNamespace(data=data, mime_type=mime_type))
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))],
        usage_metadata=SimpleNamespace(prompt_token_count=40, candidates_token_count=900),
    )


class Models:
    def __init__(self, *answers: Any) -> None:  # noqa: ANN401 - responses or exceptions
        self.answers = list(answers)
        self.prompts: list[str] = []

    async def generate_content(self, *, model: str, contents: str, config: Any) -> Any:  # noqa: ANN401
        self.prompts.append(contents)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


async def _no_sleep(_: float) -> None:
    return None


def _speech(models: Models) -> GeminiSpeech:
    return GeminiSpeech(
        models, model="tts-x", voice="Kore", timeout_s=5, max_retries=1, sleep=_no_sleep
    )


def test_wav_is_encoded_to_a_much_smaller_mp3() -> None:
    wav = _wav(2.0)
    mp3, seconds = wav_to_mp3(wav)
    assert seconds == pytest.approx(2.0)
    assert len(mp3) < len(wav) / 8
    assert mp3[:3] == b"ID3" or mp3[0] == 0xFF


async def test_gemini_narration_is_mp3_with_usage() -> None:
    models = Models(_response(_wav()))
    result = await _speech(models).synthesize("નમસ્તે", "gu")
    assert result.content_type == "audio/mpeg"
    assert result.adapter == "gemini_tts"
    assert result.call is not None
    assert (result.call.input_tokens, result.call.output_tokens) == (40, 900)
    assert "Gujarati" in models.prompts[0]


async def test_transient_errors_are_retried_and_permanent_ones_are_not() -> None:
    retried = await _speech(Models(errors.APIError(503, {}), _response(_wav()))).synthesize(
        "hi", "hi"
    )
    assert retried.seconds == pytest.approx(1.0)
    with pytest.raises(LlmUnavailableError):
        await _speech(Models(errors.APIError(400, {}))).synthesize("hi", "hi")
    with pytest.raises(LlmUnavailableError) as info:
        await _speech(
            Models(SimpleNamespace(candidates=[]), SimpleNamespace(candidates=[]))
        ).synthesize("x", "en")
    assert info.value.slug == "tts-invalid-output"


async def test_budget_guard_prices_and_caps_narration() -> None:
    ledger = InMemoryCostLedger()
    price = ModelPrice(input_inr_per_1m=Decimal(50), output_inr_per_1m=Decimal(1000))
    guarded = BudgetedSpeech(
        _speech(Models(_response(_wav()))),
        ledger,
        {"tts-x": price},
        model="tts-x",
        daily_cap_inr=1,
        clock=lambda: T0,
    )
    result = await guarded.synthesize("hello", "en")
    assert result.call is not None
    assert result.call.cost_micro_inr == 2000 + 900_000
    assert ledger.calls[T0.date()] == 1

    ledger.days[T0.date()] = 1_000_000
    with pytest.raises(BudgetExceededError):
        await guarded.synthesize("again", "en")
    unpriced = BudgetedSpeech(
        SilentSpeech(), ledger, {}, model="tts-x", daily_cap_inr=1, clock=lambda: T0
    )
    with pytest.raises(PriceUnknownError):
        await unpriced.synthesize("x", "en")


async def test_recordings_replay_by_language_voice_and_text(tmp_path: Path) -> None:
    recorder = RecordingSpeech(
        _speech(Models(_response(_wav()))), tmp_path / "case_x" / "audio_cache", voice="Kore"
    )
    original = await recorder.synthesize("हम मदद करेंगे", "hi")
    replay = ReplaySpeech(tmp_path, voice="Kore")
    again = await replay.synthesize("हम मदद करेंगे", "hi")
    assert again.audio == original.audio
    assert again.adapter == "replay"
    assert again.model == "tts-x"
    with pytest.raises(LlmUnavailableError):
        await replay.synthesize("हम मदद करेंगे", "gu")
    with pytest.raises(LlmUnavailableError):
        await ReplaySpeech(tmp_path, voice="Puck").synthesize("हम मदद करेंगे", "hi")


async def test_fake_narration_is_a_short_silent_wav() -> None:
    result = await SilentSpeech().synthesize("anything", "en")
    assert result.audio.startswith(b"RIFF")
    assert result.adapter == "fake"


def test_raw_pcm_from_older_models_is_wrapped_as_wav() -> None:
    pcm = bytes(16_000 * 2)
    wav = as_wav(pcm, "audio/L16;codec=pcm;rate=16000")
    with wave.open(io.BytesIO(wav)) as source:
        assert (source.getframerate(), source.getnframes()) == (16_000, 16_000)
    assert as_wav(wav, "audio/wav") == wav


async def test_older_models_raw_pcm_is_narrated() -> None:
    result = await _speech(Models(_response(bytes(48_000), "audio/L16;rate=24000"))).synthesize(
        "hi", "en"
    )
    assert result.seconds == pytest.approx(1.0)
