from __future__ import annotations

import unittest

from app.tts import GeminiTtsProvider, TextToSpeechService


class _StubGeminiClient:
    def __init__(self, audio: bytes) -> None:
        self._audio = audio

    def synthesize_audio(self, text: str, *, voice: str | None, mime_type: str) -> bytes:
        return self._audio


class _StubGeminiProvider(GeminiTtsProvider):
    def __init__(self, audio: bytes, languages: tuple[str, ...]) -> None:
        client = _StubGeminiClient(audio)
        super().__init__(client, languages=languages)


class TextToSpeechServiceTests(unittest.TestCase):
    def test_synthesize_uses_gemini_provider_only(self) -> None:
        provider = _StubGeminiProvider(b"gemini-audio", ("en",))
        service = TextToSpeechService(gemini_provider=provider)

        result = service.synthesize("Hello", language="en")

        self.assertEqual(result, b"gemini-audio")

    def test_auto_detect_language(self) -> None:
        provider = _StubGeminiProvider(b"gemini-audio", ("ru",))
        service = TextToSpeechService(gemini_provider=provider)

        result = service.synthesize("Привет")

        self.assertEqual(result, b"gemini-audio")

    def test_missing_provider_raises_runtime_error(self) -> None:
        service = TextToSpeechService(gemini_provider=None)

        with self.assertRaises(RuntimeError):
            service.synthesize("Hello", language="en")

    def test_unsupported_language_raises_value_error(self) -> None:
        provider = _StubGeminiProvider(b"gemini-audio", ("en",))
        service = TextToSpeechService(gemini_provider=provider)

        with self.assertRaises(ValueError):
            service.synthesize("Привет", language="ru")


if __name__ == "__main__":
    unittest.main()
