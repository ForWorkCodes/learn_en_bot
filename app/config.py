import os
from dataclasses import dataclass
from typing import Final, Optional

from dotenv import load_dotenv


@dataclass
class Settings:
    telegram_bot_token: str
    gemini_api_key: str
    gemini_model: str
    gemini_tts_model: str
    gemini_tts_voice: str
    gemini_tts_mime_type: str
    tts_prefer_gemini: bool
    database_url: str
    schedule_cron: str
    tz: str


FALSE_VALUES: Final[set[str]] = {"0", "false", "no", "off", ""}


def _to_bool(raw: Optional[str], *, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() not in FALSE_VALUES


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        gemini_tts_model=os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-tts"),
        gemini_tts_voice=os.getenv("GEMINI_TTS_VOICE", "Puck"),
        gemini_tts_mime_type=os.getenv("GEMINI_TTS_MIME_TYPE", "audio/mp3"),
        tts_prefer_gemini=_to_bool(os.getenv("TTS_PREFER_GEMINI", "true"), default=True),
        database_url=os.getenv("DATABASE_URL", "sqlite:///learn_en.db"),
        schedule_cron=os.getenv("SCHEDULE_CRON", "0 10 * * *"),
        tz=os.getenv("TZ", "UTC"),
    )

