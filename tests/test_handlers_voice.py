from __future__ import annotations

import logging
import unittest

from app.handlers.voice import send_voice_response
from app.markdown import escape


class _StubMessage:
    def __init__(self) -> None:
        self.answers: list[tuple[str, dict]] = []
        self.audios: list[object] = []

    async def answer(self, text: str, **kwargs) -> None:  # pragma: no cover - simple stub
        self.answers.append((text, kwargs))

    async def answer_audio(self, audio: object) -> None:  # pragma: no cover - simple stub
        self.audios.append(audio)


class _StubTts:
    def __init__(self, *, audio: bytes | None = None, error: Exception | None = None) -> None:
        self._audio = audio
        self._error = error

    def synthesize(self, text: str, language: str | None = None) -> bytes:
        if self._error:
            raise self._error
        return self._audio or b""


class SendVoiceResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_notifies_when_tts_raises(self) -> None:
        message = _StubMessage()
        tts = _StubTts(error=RuntimeError("boom"))
        logger = logging.getLogger("test.handlers.voice.raise")

        await send_voice_response(
            message,
            "Ответ",
            tts=tts,
            logger=logger,
            context="test",
            audio_filename="test.mp3",
        )

        self.assertEqual(len(message.audios), 0)
        self.assertEqual(
            [escape("Голосовой ответ недоступен: возникла ошибка синтеза речи.")],
            [text for text, _ in message.answers],
        )

    async def test_notifies_when_tts_returns_empty_audio(self) -> None:
        message = _StubMessage()
        tts = _StubTts(audio=b"")
        logger = logging.getLogger("test.handlers.voice.empty")

        await send_voice_response(
            message,
            "Ответ",
            tts=tts,
            logger=logger,
            context="test",
            audio_filename="test.mp3",
        )

        self.assertEqual(len(message.audios), 0)
        self.assertEqual(
            [escape("Голосовой ответ недоступен: сервис озвучки вернул пустой ответ.")],
            [text for text, _ in message.answers],
        )


if __name__ == "__main__":  # pragma: no cover - convenience for direct execution
    unittest.main()
