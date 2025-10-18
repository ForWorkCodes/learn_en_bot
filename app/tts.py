from __future__ import annotations

import logging
import re
from io import BytesIO
from typing import Optional

from gtts import gTTS


logger = logging.getLogger("learn_en_bot.tts")

_CYRILLIC_PATTERN = re.compile(r"[\u0400-\u04FF]")


class TextToSpeechService:
    """Convert short text responses into audio clips."""

    def __init__(self, default_language: str = "en", slow: bool = False) -> None:
        self.default_language = default_language
        self.slow = slow

    def synthesize(self, text: str, *, language: Optional[str] = None) -> bytes:
        clean_text = (text or "").strip()
        if not clean_text:
            raise ValueError("Cannot synthesize empty text")

        lang = language or self._detect_language(clean_text)
        try:
            tts = gTTS(text=clean_text, lang=lang, slow=self.slow)
            buffer = BytesIO()
            tts.write_to_fp(buffer)
            return buffer.getvalue()
        except Exception:
            logger.exception("Failed to synthesize speech for language %s", lang)
            raise

    def _detect_language(self, text: str) -> str:
        if _CYRILLIC_PATTERN.search(text):
            return "ru"
        return self.default_language or "en"
