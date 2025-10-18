from __future__ import annotations

import base64
import logging
from typing import Optional

import google.generativeai as genai


logger = logging.getLogger("gemini")


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        tts_model: str = "gemini-2.5-flash-tts",
    ) -> None:
        self.api_key = api_key
        self.model_name = model
        self.tts_model_name = tts_model
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
                    "Failed to initialize Gemini TTS model '%s'. Audio synthesis will be disabled.",
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
        return bool(self.tts_model)

    def synthesize_audio(self, text: str, *, voice: Optional[str] = None, mime_type: str = "audio/mp3") -> bytes:
        clean_text = (text or "").strip()
        if not clean_text:
            raise ValueError("Cannot synthesize empty text")
        if not self.tts_model:
            raise RuntimeError("Gemini TTS model is not configured")

        generation_config = genai.types.GenerationConfig(response_mime_type=mime_type)
        if voice:
            # Новые модели принимают параметр audio_voice; он будет проигнорирован, если не поддерживается.
            setattr(generation_config, "audio_voice", voice)

        try:
            response = self.tts_model.generate_content(
                clean_text,
                generation_config=generation_config,
            )
        except Exception as exc:
            logger.exception("Gemini TTS request failed: %s", exc)
            raise

        audio_bytes = self._extract_audio_from_response(response)
        if not audio_bytes:
            raise RuntimeError("Gemini TTS response did not include audio data")
        return audio_bytes

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
