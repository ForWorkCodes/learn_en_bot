import google.generativeai as genai
from typing import Optional
import logging


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-2.5-pro") -> None:
        self.api_key = api_key
        self.model_name = model
        if not api_key:
            # Оставляем возможность работать без ключа — вернём заглушки
            self.model = None
        else:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(self.model_name)

    def generate(self, prompt: str, fallback: str = "") -> str:
        if not self.model:
            logging.getLogger("gemini").warning("GEMINI_API_KEY is not set; returning fallback")
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
            logging.getLogger("gemini").exception("Gemini generate error: %s", e)
            return fallback or f"(Gemini error: {e})"

    def daily_tip(self) -> str:
        prompt = (
            "Сгенерируй короткий (1-2 предложения) совет по изучению английского языка. "
            "Без лишних префиксов, на русском, дружелюбно."
        )
        return self.generate(prompt, fallback="Совет дня: выучи 3 новых слова и составь с ними предложения.")

    def generate_phrasal_verb(self, user_hint: str | None = None) -> dict:
        prompt = (
            "Подбери один английский фразовый глагол для изучения сегодня. "
            "Ответ дай строго в JSON с полями: verb (строка), translation (краткий перевод на русский), "
            "explanation (короткое дружелюбное объяснение на русском), examples (массив из 2-3 коротких примеров на английском)."
        )
        if user_hint:
            prompt += f"\nУчти информацию о пользователе: {user_hint}."
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
                "explanation": "Часто значит усвоить что-то по ходу дела или поднять с земли.",
                "examples": [
                    "She picked up Spanish while living in Madrid.",
                    "Please pick up the book from the floor.",
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
