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
        mime_type: str = "audio/ogg; codecs=opus",
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
        gemini_provider: Optional["GeminiTtsProvider"] = None,
        fallback_provider: Optional[object] = None,
        default_language: str = "en",
    ) -> None:
        self.gemini_provider = gemini_provider
        self.fallback_provider = fallback_provider
        self.default_language = default_language

    def synthesize(self, text: str, *, language: Optional[str] = None) -> bytes:
        clean_text = (text or "").strip()
        if not clean_text:
            raise ValueError("Cannot synthesize empty text")

        lang = (language or self._detect_language(clean_text)).lower()

        # Try Gemini first if configured and supports the language
        if self.gemini_provider and self.gemini_provider.supports_language(lang):
            try:
                return self._synthesize_gemini(clean_text, lang)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Gemini TTS failed; will try fallback provider if available",
                    exc_info=exc,
                )

        # Fallback provider (e.g., Google Cloud TTS)
        if self.fallback_provider and self.fallback_provider.supports_language(lang):
            return self.fallback_provider.synthesize(clean_text, language=lang)

        # If we got here, no provider is available
        if not self.gemini_provider and not self.fallback_provider:
            logger.error("No TTS providers are configured")
            raise RuntimeError("No TTS providers are configured")

        logger.error("No configured TTS provider supports language %s", lang)
        raise ValueError(f"Language '{lang}' is not supported by configured TTS providers")

    def _detect_language(self, text: str) -> str:
        if _CYRILLIC_PATTERN.search(text):
            return "ru"
        return self.default_language or "en"

    def _synthesize_gemini(self, text: str, language: str) -> bytes:
        if not self.gemini_provider:
            raise RuntimeError("Gemini provider is not configured")
        return self.gemini_provider.synthesize(text, language=language)


class GoogleCloudTtsProvider:
    """Google Cloud Text-to-Speech provider (stable, reliable).

    Requires GOOGLE_APPLICATION_CREDENTIALS to be set and readable.
    """

    def __init__(
        self,
        *,
        voice: Optional[str] = None,
        language_code: str = "en-US",
        audio_encoding: str = "MP3",  # "MP3" or "OGG_OPUS"
        languages: Sequence[str] = ("en", "ru"),
    ) -> None:
        self._voice = voice  # e.g., "en-US-Neural2-C"; if None, auto-select by language
        self._language_code = language_code
        self._audio_encoding = audio_encoding
        self._languages = tuple(lang.lower() for lang in languages if lang)

        # Lazy import to avoid mandatory dependency if unused
        try:
            from google.cloud import texttospeech  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            # Defer actual failure until synthesize is called
            logger.debug("google-cloud-texttospeech import deferred: %s", exc)

    def supports_language(self, language: str) -> bool:
        normalized = (language or "").lower()
        return any(normalized.startswith(prefix) for prefix in self._languages)

    def synthesize(self, text: str, *, language: str) -> bytes:
        from google.cloud import texttospeech

        lang_code = self._pick_language_code(language)

        synthesis_input = texttospeech.SynthesisInput(text=text)

        voice_params = {}
        if self._voice:
            voice_params["name"] = self._voice
            # If specific voice includes a locale, do not override
            if "-" in self._voice:
                voice_params.setdefault("language_code", self._voice.split("-", 2)[0] + "-" + self._voice.split("-", 2)[1])
        voice = texttospeech.VoiceSelectionParams(
            language_code=voice_params.get("language_code", lang_code),
            name=voice_params.get("name", None),
        )

        encoding = self._audio_encoding.upper().replace(" ", "_")
        if encoding not in {"MP3", "OGG_OPUS"}:
            encoding = "MP3"
        audio_config = texttospeech.AudioConfig(
            audio_encoding=getattr(texttospeech.AudioEncoding, encoding),
        )

        client = texttospeech.TextToSpeechClient()
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )
        return bytes(response.audio_content)

    def _pick_language_code(self, language: str) -> str:
        # Map simple language codes to Cloud TTS locales
        normalized = (language or "").lower()
        if normalized.startswith("ru"):
            return "ru-RU"
        if normalized.startswith("en"):
            return "en-US"
        return self._language_code or "en-US"


class GTTSTtsProvider:
    """gTTS-based provider (no credentials required).

    Produces MP3 audio for supported languages via Google Translate TTS.
    """

    def __init__(
        self,
        *,
        languages: Sequence[str] = ("en", "ru"),
    ) -> None:
        self._languages = tuple(lang.lower() for lang in languages if lang)

        try:
            import gtts  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            # Defer failure until synthesize is called
            logger.debug("gTTS import deferred: %s", exc)

    def supports_language(self, language: str) -> bool:
        normalized = (language or "").lower()
        return any(normalized.startswith(prefix) for prefix in self._languages)

    def synthesize(self, text: str, *, language: str) -> bytes:
        from gtts import gTTS
        from io import BytesIO

        lang_code = self._pick_lang(language)
        buf = BytesIO()
        tts = gTTS(text=text, lang=lang_code)
        tts.write_to_fp(buf)
        return buf.getvalue()

    def _pick_lang(self, language: str) -> str:
        normalized = (language or "").lower()
        if normalized.startswith("ru"):
            return "ru"
        return "en"
