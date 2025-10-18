from __future__ import annotations

import base64
import pathlib
import sys
import unittest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from app.gemini import GeminiClient
from app.tts import GeminiTtsProvider, TextToSpeechService


class _StubGeminiClient:
    def __init__(self, audio: bytes) -> None:
        self._audio = audio

    def synthesize_audio(self, text: str, *, voice: str | None, mime_type: str) -> bytes:
        return self._audio


class _RecordingModel:
    def __init__(self, response: object) -> None:
        self._response = response
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def generate_content(self, *args: object, **kwargs: object) -> object:
        self.calls.append((args, kwargs))
        return self._response


def _fake_audio_response(payload: object) -> object:
    inline_data = type("InlineData", (), {"data": payload})
    part = type("Part", (), {"inline_data": inline_data})
    content = type("Content", (), {"parts": [part]})
    candidate = type("Candidate", (), {"content": content})
    return type("Response", (), {"candidates": [candidate]})()


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

    def test_default_provider_supports_russian(self) -> None:
        provider = GeminiTtsProvider(_StubGeminiClient(b"gemini-audio"))
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


class GeminiClientAudioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = GeminiClient(api_key="")

    def test_synthesize_audio_uses_audio_kwargs(self) -> None:
        response = _fake_audio_response(b"audio-bytes")
        model = _RecordingModel(response)
        self.client.tts_model = model

        result = self.client.synthesize_audio("Hello", voice="Puck", mime_type="audio/ogg")

        self.assertEqual(result, b"audio-bytes")
        self.assertEqual(len(model.calls), 1)
        args, kwargs = model.calls[0]
        self.assertEqual(args, ("Hello",))
        self.assertEqual(kwargs["response_mime_type"], "audio/ogg")
        self.assertEqual(kwargs["speech_config"], {"voice": "Puck"})

    def test_synthesize_audio_decodes_base64_payload(self) -> None:
        payload = base64.b64encode(b"audio-stream").decode("ascii")
        response = _fake_audio_response(payload)
        model = _RecordingModel(response)
        self.client.tts_model = model

        result = self.client.synthesize_audio("Hello", mime_type="audio/mp3")

        self.assertEqual(result, b"audio-stream")
        _, kwargs = model.calls[0]
        self.assertNotIn("speech_config", kwargs)


if __name__ == "__main__":
    unittest.main()
