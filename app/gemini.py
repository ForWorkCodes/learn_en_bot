from __future__ import annotations

import base64
import json
import logging
from typing import Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

import google.generativeai as genai


logger = logging.getLogger("gemini")


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        tts_model: str = "gemini-2.5-flash-preview-tts",
        *,
        tts_timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model_name = model
        self.tts_model_name = tts_model
        self._tts_timeout = tts_timeout
        self.model: Optional[genai.GenerativeModel]
        self.tts_model: Optional[genai.GenerativeModel]
        if not api_key:
            # Оставляем возможность работать без ключа — вернём заглушки
            self.model = None
            self.tts_model = None
        else:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(self.model_name)
            try:
                self.tts_model = genai.GenerativeModel(self.tts_model_name) if tts_model else None
            except Exception:
                logger.warning(
                    "Failed to initialize Gemini TTS model '%s'. Audio synthesis will fallback to direct HTTP requests.",
                    self.tts_model_name,
                    exc_info=True,
                )
                self.tts_model = None

    def generate(self, prompt: str, fallback: str = "") -> str:
        if not self.model:
            logger.warning("GEMINI_API_KEY is not set; returning fallback")
            return fallback or "(No GEMINI_API_KEY set — returning placeholder)"
        try:
            response = self.model.generate_content(prompt)
            # google-generativeai может возвращать список кандидатов; используем текст
            text = getattr(response, "text", None)
            if text:
                return text.strip()
            # fallback на raw
            return str(response)
        except Exception as e:
            logger.exception("Gemini generate error: %s", e)
            return fallback or f"(Gemini error: {e})"

    @property
    def supports_audio(self) -> bool:
        return bool(self.tts_model or (self.api_key and self.tts_model_name))

    def synthesize_audio(
        self,
        text: str,
        *,
        voice: Optional[str] = None,
        mime_type: str = "audio/ogg; codecs=opus",
    ) -> bytes:
        clean_text = (text or "").strip()
        if not clean_text:
            raise ValueError("Cannot synthesize empty text")
        if not self.tts_model:
            logger.debug("Gemini SDK TTS model is unavailable; using direct HTTP request")
            return self._synthesize_audio_via_http(clean_text, mime_type=mime_type, voice=voice)

        generation_config: dict[str, object] = {
            "response_mime_type": mime_type,
            "response_modalities": ["AUDIO"],
        }

        if voice:
            generation_config["speech_config"] = {
                "voice_config": {"voice_name": voice}
            }

        try:
            response = self.tts_model.generate_content(
                clean_text,
                generation_config=generation_config,
            )
            audio_bytes = self._extract_audio_from_response(response)
            if audio_bytes:
                return audio_bytes
            logger.warning("Gemini SDK TTS response did not include audio; retrying over HTTP")
        except Exception:
            logger.exception("Gemini SDK TTS synthesis failed; retrying over HTTP")

        return self._synthesize_audio_via_http(clean_text, mime_type=mime_type, voice=voice)

    def _synthesize_audio_via_http(
        self,
        text: str,
        *,
        mime_type: str,
        voice: Optional[str],
    ) -> bytes:
        if not self.api_key:
            raise RuntimeError("Gemini API key is not configured; cannot call TTS endpoint")

        def perform_request(payload: dict[str, object], endpoint: str) -> bytes:
            request_data = json.dumps(payload).encode("utf-8")
            http_request = urllib_request.Request(
                endpoint,
                data=request_data,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                },
            )

            try:
                with urllib_request.urlopen(http_request, timeout=self._tts_timeout) as response:
                    raw_body = response.read()
            except urllib_error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="ignore")
                logger.error(
                    "Gemini HTTP TTS request failed with status %s: %s",
                    exc.code,
                    error_body,
                )
                raise RuntimeError(
                    f"Gemini HTTP TTS request failed with status {exc.code}: {error_body}"
                ) from exc
            except urllib_error.URLError as exc:
                logger.error("Gemini HTTP TTS request failed: %s", exc)
                raise RuntimeError("Gemini HTTP TTS request failed") from exc

            try:
                response_payload = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError as exc:
                logger.error("Failed to decode Gemini HTTP TTS response: %s", exc)
                raise RuntimeError("Gemini HTTP TTS response was not valid JSON") from exc

            audio_bytes_inner = self._extract_audio_from_json(response_payload)
            if not audio_bytes_inner:
                logger.error("Gemini HTTP TTS response did not contain audio data")
                raise RuntimeError("Gemini HTTP TTS response did not contain audio data")
            return audio_bytes_inner

        base_payload: dict[str, object] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": text,
                        }
                    ],
                }
            ],
            "generationConfig": {
                "responseMimeType": mime_type,
                "responseModalities": ["AUDIO"],
            },
        }

        endpoints: list[tuple[str, dict[str, object], str]] = []

        # Primary endpoint: Responses API (newer surface that allows audio + voices).
        responses_payload = json.loads(json.dumps(base_payload))
        responses_payload["model"] = f"models/{self.tts_model_name}"
        if voice:
            speech_config = responses_payload.setdefault("speechConfig", {})
            speech_config["voiceConfig"] = {"voiceName": voice}
        endpoints.append(
            (
                "https://generativelanguage.googleapis.com/v1beta/responses:generate",
                responses_payload,
                "Responses API",
            )
        )

        # Legacy endpoint: generateContent. Remove fields unsupported by the legacy schema.
        legacy_payload = json.loads(json.dumps(base_payload))
        legacy_generation_cfg = legacy_payload.get("generationConfig", {})
        legacy_generation_cfg.pop("responseModalities", None)
        if voice:
            generation_config = legacy_payload.setdefault("generationConfig", {})
            audio_config = generation_config.setdefault("audioConfig", {})
            audio_config["voiceConfig"] = {"voiceName": voice}
        legacy_endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.tts_model_name}:generateContent"
        )
        endpoints.append((legacy_endpoint, legacy_payload, "generateContent"))

        last_error: Optional[Exception] = None
        for endpoint, payload, label in endpoints:
            try:
                return perform_request(payload, endpoint)
            except RuntimeError as exc:
                last_error = exc
                logger.warning(
                    "%s TTS request failed (%s).", label, exc
                )
                if voice and label == "generateContent":
                    logger.warning("Retrying legacy endpoint without explicit voice configuration.")
                    stripped_payload = json.loads(json.dumps(legacy_payload))
                    stripped_generation = stripped_payload.get("generationConfig", {})
                    if "audioConfig" in stripped_generation:
                        stripped_generation.pop("audioConfig", None)
                    try:
                        return perform_request(stripped_payload, endpoint)
                    except RuntimeError as exc_inner:
                        last_error = exc_inner
                        logger.warning(
                            "Legacy generateContent TTS without voice still failed (%s).",
                            exc_inner,
                        )

        raise RuntimeError("Gemini HTTP TTS request failed") if last_error is None else last_error

    @staticmethod
    def _extract_audio_from_response(response: genai.types.GenerateContentResponse) -> bytes:
        try:
            candidates = response.candidates
        except Exception:
            response.resolve()
            candidates = response.candidates

        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", []) if content else []
            for part in parts:
                inline_data = getattr(part, "inline_data", None)
                if not inline_data:
                    continue
                data = getattr(inline_data, "data", b"")
                if isinstance(data, bytes) and data:
                    return data
                if isinstance(data, str) and data:
                    try:
                        return base64.b64decode(data)
                    except Exception:
                        logger.debug("Failed to base64-decode audio payload from Gemini response")
        return b""

    @staticmethod
    def _extract_audio_from_json(payload: dict[str, object]) -> bytes:
        candidates: list | None = None
        if isinstance(payload, dict):
            primary = payload.get("candidates")
            if isinstance(primary, list):
                candidates = primary
            else:
                output = payload.get("output")
                if isinstance(output, list):
                    candidates = output
        if not candidates:
            return b""

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content")
            if not isinstance(content, dict):
                continue
            parts = content.get("parts")
            if not isinstance(parts, list):
                continue
            for part in parts:
                if not isinstance(part, dict):
                    continue
                inline_data = part.get("inlineData")
                if not isinstance(inline_data, dict):
                    continue
                data = inline_data.get("data")
                if isinstance(data, str) and data:
                    try:
                        return base64.b64decode(data)
                    except Exception:
                        logger.debug("Failed to base64-decode audio payload from Gemini JSON response")
                elif isinstance(data, bytes) and data:
                    return data
        return b""

    def daily_tip(self) -> str:
        prompt = (
            "Сгенерируй короткий (1-2 предложения) совет по изучению английского языка. "
            "Без лишних префиксов, на русском, дружелюбно."
        )
        return self.generate(prompt, fallback="Совет дня: выучи 3 новых слова и составь с ними предложения.")

    def generate_phrasal_verb(self) -> dict:
        prompt = (
            "Подбери один английский фразовый глагол для изучения сегодня. "
            "Ответ дай строго в JSON с полями: "
            "verb (строка), translation (краткий перевод на русский), "
            "explanation (короткое пояснение на русском без приветствий и обращений), "
            "examples (массив из 2-3 объектов с полями text и translation, где text — предложение на английском, "
            "а translation — краткий перевод на русский)."
        )
        raw = self.generate(prompt)
        import json, re
        # Попытаться извлечь JSON из ответа
        try:
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                raw = m.group(0)
            data = json.loads(raw)
            if not all(k in data for k in ("verb", "translation", "explanation", "examples")):
                raise ValueError("missing keys")
            if not isinstance(data.get("examples"), list):
                raise ValueError("examples must be list")
            return data
        except Exception:
            # Fallback минимально валидный
            return {
                "verb": "pick up",
                "translation": "подобрать; выучить",
                "explanation": "Этот фразовый глагол означает выучить что-то по ходу дела или поднять предмет.",
                "examples": [
                    {
                        "text": "She picked up Spanish while living in Madrid.",
                        "translation": "Она освоила испанский, пока жила в Мадриде.",
                    },
                    {
                        "text": "Please pick up the book from the floor.",
                        "translation": "Пожалуйста, подними книгу с пола.",
                    },
                ],
            }

    def evaluate_usage(self, verb: str, user_text: str) -> tuple[str, bool]:
        prompt = (
            "Оцени, верно ли пользователь использует фразовый глагол. "
            "Дай краткую обратную связь на русском и выставь оценку от 1 до 5. "
            "Формат ответa строго: JSON с полями feedback (строка), score (число 1-5).\n"
            f"Целевой фразовый глагол: {verb}\n"
            f"Ответ пользователя: {user_text}\n"
        )
        raw = self.generate(prompt)
        import json, re
        try:
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                raw = m.group(0)
            data = json.loads(raw)
            feedback = str(data.get("feedback", ""))
            score = int(data.get("score", 0))
            mastered = score >= 4
            if not feedback:
                feedback = "Хорошая попытка! Попробуй составить ещё одно предложение."
            return feedback, mastered
        except Exception:
            return (
                "Спасибо! Постарайся составить короткое предложение с этим фразовым глаголом.",
                False,
            )
