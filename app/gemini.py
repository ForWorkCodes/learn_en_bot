import google.generativeai as genai
from typing import Optional


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash") -> None:
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
            return fallback or f"(Gemini error: {e})"

    def daily_tip(self) -> str:
        prompt = (
            "Сгенерируй короткий (1-2 предложения) совет по изучению английского языка. "
            "Без лишних префиксов, на русском, дружелюбно."
        )
        return self.generate(prompt, fallback="Совет дня: выучи 3 новых слова и составь с ними предложения.")

