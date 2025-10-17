import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class Settings:
    telegram_bot_token: str
    gemini_api_key: str
    database_url: str
    schedule_cron: str
    tz: str


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        database_url=os.getenv("DATABASE_URL", "sqlite:///learn_en.db"),
        schedule_cron=os.getenv("SCHEDULE_CRON", "0 10 * * *"),
        tz=os.getenv("TZ", "UTC"),
    )

