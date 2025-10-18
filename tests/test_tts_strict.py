import sys
import types
import unittest
from unittest.mock import patch


if "edge_tts" not in sys.modules:  # pragma: no cover - test isolation
    edge_stub = types.ModuleType("edge_tts")

    class _DummyCommunicate:  # pragma: no cover - test isolation
        def __init__(self, *args, **kwargs) -> None:
            pass

        def stream(self):  # pragma: no cover - never used in these tests
            raise NotImplementedError

    edge_stub.Communicate = _DummyCommunicate
    sys.modules["edge_tts"] = edge_stub

if "gtts" not in sys.modules:  # pragma: no cover - test isolation
    gtts_stub = types.ModuleType("gtts")

    class _DummyGTTS:  # pragma: no cover - test isolation
        def __init__(self, *args, **kwargs) -> None:
            pass

        def write_to_fp(self, fp) -> None:
            raise NotImplementedError

    gtts_stub.gTTS = _DummyGTTS
    sys.modules["gtts"] = gtts_stub

from app.tts import TextToSpeechService


class _StubGeminiProvider:
    def __init__(self, audio: bytes, supported_languages: tuple[str, ...] = ("en",)) -> None:
        self._audio = audio
        self._languages = {lang.lower() for lang in supported_languages}

    def supports_language(self, language: str) -> bool:  # pragma: no cover - trivial
        return language.lower() in self._languages

    def synthesize(self, text: str, *, language: str) -> bytes:
        return self._audio


class TextToSpeechServiceStrictGeminiTests(unittest.TestCase):
    def test_strict_mode_returns_gemini_audio_without_fallback(self) -> None:
        provider = _StubGeminiProvider(b"gemini-audio")
        service = TextToSpeechService(
            gemini_provider=provider,
            prefer_gemini=True,
            strict_gemini=True,
        )

        with patch.object(service, "_synthesize_edge") as synth_edge, patch.object(
            service, "_synthesize_gtts"
        ) as synth_gtts:
            result = service.synthesize("Hello", language="en")

        self.assertEqual(result, b"gemini-audio")
        synth_edge.assert_not_called()
        synth_gtts.assert_not_called()

    def test_strict_mode_without_provider_returns_empty_and_skips_fallback(self) -> None:
        service = TextToSpeechService(
            gemini_provider=None,
            prefer_gemini=True,
            strict_gemini=True,
        )

        with patch.object(service, "_synthesize_edge") as synth_edge, patch.object(
            service, "_synthesize_gtts"
        ) as synth_gtts:
            result = service.synthesize("Hello", language="en")

        self.assertEqual(result, b"")
        synth_edge.assert_not_called()
        synth_gtts.assert_not_called()

    def test_strict_mode_propagates_gemini_error_without_fallback(self) -> None:
        provider = _StubGeminiProvider(b"ignored")
        service = TextToSpeechService(
            gemini_provider=provider,
            prefer_gemini=True,
            strict_gemini=True,
        )

        with (
            patch.object(service, "_synthesize_gemini", side_effect=RuntimeError("boom")) as synth_gemini,
            patch.object(service, "_synthesize_edge") as synth_edge,
            patch.object(service, "_synthesize_gtts") as synth_gtts,
        ):
            result = service.synthesize("Hello", language="en")

        self.assertEqual(result, b"")
        synth_gemini.assert_called_once()
        synth_edge.assert_not_called()
        synth_gtts.assert_not_called()


if __name__ == "__main__":  # pragma: no cover - convenience
    unittest.main()
