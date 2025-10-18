from __future__ import annotations

import asyncio
import logging
import re
from io import BytesIO
from typing import Optional, Sequence, TYPE_CHECKING

import edge_tts
from gtts import gTTS


if TYPE_CHECKING:
    from .gemini import GeminiClient


logger = logging.getLogger("learn_en_bot.tts")

_CYRILLIC_PATTERN = re.compile(r"[\u0400-\u04FF]")


class GeminiTtsProvider:
    """Adapter around GeminiClient to synthesize high-quality speech."""

    def __init__(
        self,
        client: "GeminiClient",
        *,
        voice: Optional[str] = None,
        mime_type: str = "audio/mp3",
        languages: Sequence[str] = ("en",),
    ) -> None:
        self._client = client
        self.voice = voice
        self.mime_type = mime_type
        self._languages = tuple(lang.lower() for lang in languages if lang)

    def supports_language(self, language: str) -> bool:
        normalized = (language or "").lower()
        return any(normalized.startswith(prefix) for prefix in self._languages)

    def synthesize(self, text: str, *, language: str) -> bytes:
        if not self.supports_language(language):
            raise ValueError(f"Language '{language}' is not supported by Gemini TTS provider")
        return self._client.synthesize_audio(text, voice=self.voice, mime_type=self.mime_type)


class TextToSpeechService:
    """Convert short text responses into audio clips."""

    def __init__(
        self,
        default_language: str = "en",
        slow: bool = False,
        english_voice: str = "en-US-AriaNeural",
        english_rate: str = "+0%",
        gemini_provider: Optional[GeminiTtsProvider] = None,
        prefer_gemini: bool = True,
    ) -> None:
        self.default_language = default_language
        self.slow = slow
        self.english_voice = english_voice
        self.english_rate = english_rate
        self.gemini_provider = gemini_provider
        self.prefer_gemini = prefer_gemini

    def synthesize(self, text: str, *, language: Optional[str] = None) -> bytes:
        clean_text = (text or "").strip()
        if not clean_text:
            raise ValueError("Cannot synthesize empty text")

        lang = (language or self._detect_language(clean_text)).lower()

        if self._should_use_gemini(lang):
            try:
                return self._synthesize_gemini(clean_text, lang)
            except Exception:
                logger.exception("Gemini TTS failed for language %s; falling back to other providers", lang)

        if self._should_use_edge(lang):
            try:
                return self._synthesize_edge(clean_text, lang)
            except Exception:
                logger.exception("Edge TTS failed for language %s; falling back to gTTS", lang)

        try:
            return self._synthesize_gtts(clean_text, lang)
        except Exception:
            logger.exception("Failed to synthesize speech for language %s", lang)
            raise

    def _detect_language(self, text: str) -> str:
        if _CYRILLIC_PATTERN.search(text):
            return "ru"
        return self.default_language or "en"

    def _should_use_gemini(self, language: str) -> bool:
        if not self.prefer_gemini or not self.gemini_provider:
            return False
        return self.gemini_provider.supports_language(language)

    def _should_use_edge(self, language: str) -> bool:
        return language.startswith("en")

    def _synthesize_gemini(self, text: str, language: str) -> bytes:
        if not self.gemini_provider:
            raise RuntimeError("Gemini provider is not configured")
        return self.gemini_provider.synthesize(text, language=language)

    def _synthesize_gtts(self, text: str, language: str) -> bytes:
        tts = gTTS(text=text, lang=language, slow=self.slow)
        buffer = BytesIO()
        tts.write_to_fp(buffer)
        return buffer.getvalue()

    def _synthesize_edge(self, text: str, language: str) -> bytes:
        voice = self._resolve_edge_voice(language)
        logger.debug("Synthesizing speech via Edge TTS using voice %s", voice)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._stream_edge_audio(text, voice=voice, rate=self.english_rate))

        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            return new_loop.run_until_complete(
                self._stream_edge_audio(text, voice=voice, rate=self.english_rate)
            )
        finally:
            new_loop.close()
            asyncio.set_event_loop(None)

    async def _stream_edge_audio(self, text: str, voice: str, rate: str) -> bytes:
        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
        audio_stream = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_stream.extend(chunk["data"])
        if not audio_stream:
            raise RuntimeError("Edge TTS produced no audio data")
        return bytes(audio_stream)

    def _resolve_edge_voice(self, language: str) -> str:
        if language.startswith("en-gb"):
            return "en-GB-LibbyNeural"
        if language.startswith("en-au"):
            return "en-AU-NatashaNeural"
        return self.english_voice
