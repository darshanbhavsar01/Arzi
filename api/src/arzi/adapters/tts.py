"""Narrated audio: Gemini TTS (live), recorded audio (replay), silence (fake).

Gemini returns a 24 kHz mono WAV; it is encoded once to 32 kbps MP3 (a fifteenth of the size,
still clear speech)
so the family page plays quickly on a phone. Recordings are keyed by language, voice and the
exact rendered text, not by model, like the text recordings.
"""

import datetime as dt
import hashlib
import io
import json
import logging
import random
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio

from arzi.adapters.genai_client import RETRYABLE_STATUS, Sleep
from arzi.domain.models import LlmCall
from arzi.services.cost_ledger import (
    BudgetExceededError,
    PriceTable,
    PriceUnknownError,
    estimate_micro_inr,
    today_ist,
)
from arzi.services.ports import CostLedgerStore, LlmUnavailableError, SpeechResult

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {"en": "Indian English", "hi": "Hindi", "gu": "Gujarati"}


def speech_key(text: str, lang: str, voice: str) -> str:
    return hashlib.sha256(json.dumps([lang, voice, text]).encode()).hexdigest()


def as_wav(data: bytes, mime_type: str) -> bytes:
    """Newer TTS models return a WAV; older ones raw 16-bit mono PCM (``audio/L16;rate=24000``)."""
    if data.startswith(b"RIFF"):
        return data
    rate = 24_000
    for param in mime_type.split(";"):
        key, _, value = param.strip().partition("=")
        if key == "rate" and value.isdigit():
            rate = int(value)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(data)
    return buffer.getvalue()


def wav_to_mp3(wav: bytes) -> tuple[bytes, float]:
    """Encode a mono 16-bit WAV to MP3; returns the MP3 and its duration in seconds."""
    import lameenc

    with wave.open(io.BytesIO(wav)) as source:
        rate, frames = source.getframerate(), source.readframes(source.getnframes())
        seconds = source.getnframes() / rate
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(32)
    encoder.set_in_sample_rate(rate)
    encoder.set_channels(1)
    encoder.set_quality(2)
    return bytes(encoder.encode(frames) + encoder.flush()), seconds


class GeminiSpeech:
    """Gemini TTS with a prebuilt voice; same timeout and retry policy as text calls."""

    def __init__(
        self,
        models: Any,  # noqa: ANN401 - the SDK's async models API (ClientModels)
        *,
        model: str,
        voice: str,
        timeout_s: float,
        max_retries: int,
        sleep: Sleep = anyio.sleep,
    ) -> None:
        self._models = models
        self._model = model
        self._voice = voice
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._sleep = sleep

    async def synthesize(self, text: str, lang: str) -> SpeechResult:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self._voice)
                )
            ),
        )
        prompt = f"Read this aloud in {LANGUAGE_NAMES.get(lang, lang)}, warmly and slowly:\n{text}"
        for attempt in range(self._max_retries + 1):
            try:
                with anyio.fail_after(self._timeout_s):
                    response = await self._models.generate_content(
                        model=self._model, contents=prompt, config=config
                    )
                inline = response.candidates[0].content.parts[0].inline_data
                data = as_wav(inline.data, inline.mime_type or "")
                mp3, seconds = await anyio.to_thread.run_sync(wav_to_mp3, data)
                usage = response.usage_metadata
                call = LlmCall(
                    prompt_ref=f"tts_{lang}",
                    model=self._model,
                    input_tokens=getattr(usage, "prompt_token_count", None) or 0,
                    output_tokens=getattr(usage, "candidates_token_count", None) or 0,
                )
                return SpeechResult(mp3, "audio/mpeg", seconds, self._model, "gemini_tts", call)
            except errors.APIError as exc:
                retryable, slug = exc.code in RETRYABLE_STATUS, "tts-error"
            except TimeoutError:
                retryable, slug = True, "tts-timeout"
            except (AttributeError, IndexError, TypeError, wave.Error):
                retryable, slug = True, "tts-invalid-output"
            logger.warning("tts call %s failed (%s), attempt %d", lang, slug, attempt + 1)
            if not retryable or attempt == self._max_retries:
                raise LlmUnavailableError(slug)
            await self._sleep((2**attempt) * (1 + random.random()))  # noqa: S311 - jitter only
        raise LlmUnavailableError("tts-error")  # pragma: no cover - the loop returns or raises


class BudgetedSpeech:
    """Refuse when over the daily budget, price each narration, add it to the ledger."""

    def __init__(
        self,
        inner: Any,  # noqa: ANN401 - any SpeechClient
        ledger: CostLedgerStore,
        prices: PriceTable,
        *,
        model: str,
        daily_cap_inr: int,
        clock: Callable[[], dt.datetime],
    ) -> None:
        self._inner = inner
        self._ledger = ledger
        self._prices = prices
        self._model = model
        self._cap_micro = daily_cap_inr * 1_000_000
        self._clock = clock

    async def synthesize(self, text: str, lang: str) -> SpeechResult:
        price = self._prices.get(self._model)
        if price is None:
            raise PriceUnknownError(self._model)
        day = today_ist(self._clock)
        if await self._ledger.spent_micro_inr(day) >= self._cap_micro:
            raise BudgetExceededError
        result: SpeechResult = await self._inner.synthesize(text, lang)
        if result.call is None:  # pragma: no cover - the live adapter always reports usage
            return result
        call = result.call.model_copy(
            update={"cost_micro_inr": estimate_micro_inr(result.call, price)}
        )
        await self._ledger.add(day, call)
        return SpeechResult(
            result.audio, result.content_type, result.seconds, result.model, result.adapter, call
        )


class ReplaySpeech:
    """Recorded narrations: ``<root>/*/audio_cache/<key>.mp3`` with a ``.json`` sidecar."""

    def __init__(self, root: Path, *, voice: str) -> None:
        self._root = root
        self._voice = voice

    async def synthesize(self, text: str, lang: str) -> SpeechResult:
        key = speech_key(text, lang, self._voice)
        matches = sorted(self._root.glob(f"*/audio_cache/{key}.json"))
        if not matches:
            raise LlmUnavailableError("replay-miss")
        meta = json.loads(await anyio.Path(matches[0]).read_text(encoding="utf-8"))
        audio = await anyio.Path(matches[0].with_suffix(".mp3")).read_bytes()
        return SpeechResult(
            audio, "audio/mpeg", float(meta["seconds"]), str(meta["model"]), "replay"
        )


class RecordingSpeech:
    """Passes narrations through and saves each one for replay."""

    def __init__(self, inner: Any, directory: Path, *, voice: str) -> None:  # noqa: ANN401
        self._inner = inner
        self._directory = directory
        self._voice = voice

    async def synthesize(self, text: str, lang: str) -> SpeechResult:
        result: SpeechResult = await self._inner.synthesize(text, lang)
        self._directory.mkdir(parents=True, exist_ok=True)
        key = speech_key(text, lang, self._voice)
        (self._directory / f"{key}.mp3").write_bytes(result.audio)
        meta = {
            "lang": lang,
            "voice": self._voice,
            "model": result.model,
            "seconds": round(result.seconds, 2),
        }
        (self._directory / f"{key}.json").write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        return result


class SilentSpeech:
    """``fake`` mode: a short silent WAV, so the family page and its tests run offline."""

    async def synthesize(self, text: str, lang: str) -> SpeechResult:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(8000)
            out.writeframes(bytes(8000))
        return SpeechResult(buffer.getvalue(), "audio/wav", 0.5, "silence", "fake")
