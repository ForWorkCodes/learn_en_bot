from __future__ import annotations

import logging
import re
from typing import Optional, Sequence, TYPE_CHECKING


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
        languages: Sequence[str] = ("en", "ru"),
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
    """Convert short text responses into audio clips using Gemini only."""

    def __init__(
        self,
        *,
        gemini_provider: Optional[GeminiTtsProvider] = None,
        default_language: str = "en",
    ) -> None:
        self.gemini_provider = gemini_provider
        self.default_language = default_language

    def synthesize(self, text: str, *, language: Optional[str] = None) -> bytes:
        clean_text = (text or "").strip()
        if not clean_text:
            raise ValueError("Cannot synthesize empty text")

        lang = (language or self._detect_language(clean_text)).lower()

        if not self.gemini_provider:
            logger.error("Gemini TTS provider is not configured")
            raise RuntimeError("Gemini TTS provider is not configured")

        if not self.gemini_provider.supports_language(lang):
            logger.error("Gemini TTS provider does not support language %s", lang)
            raise ValueError(f"Language '{lang}' is not supported by Gemini TTS provider")

        return self._synthesize_gemini(clean_text, lang)

    def _detect_language(self, text: str) -> str:
        if _CYRILLIC_PATTERN.search(text):
            return "ru"
        return self.default_language or "en"

    def _synthesize_gemini(self, text: str, language: str) -> bytes:
        if not self.gemini_provider:
            raise RuntimeError("Gemini provider is not configured")
        return self.gemini_provider.synthesize(text, language=language)
