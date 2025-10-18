from __future__ import annotations

import asyncio
import logging

from aiogram import types

from ..markdown import escape
from ..tts import TextToSpeechService


async def notify_voice_unavailable(
    message: types.Message,
    *,
    logger: logging.Logger,
    context: str,
    user_reason: str,
    technical_reason: str | None = None,
    exc: BaseException | None = None,
) -> None:
    """Log and notify the user that a voice reply cannot be delivered."""

    log_reason = technical_reason or user_reason
    if exc:
        logger.error(
            "Voice reply unavailable for %s: %s",
            context,
            log_reason,
            exc_info=exc,
        )
    else:
        logger.warning(
            "Voice reply unavailable for %s: %s",
            context,
            log_reason,
        )

    notification = escape(
        f"Голосовой ответ недоступен: {user_reason}."
    )
    await message.answer(notification)


async def send_voice_response(
    message: types.Message,
    plain_text: str | None,
    *,
    tts: TextToSpeechService,
    logger: logging.Logger,
    context: str,
    audio_filename: str,
) -> None:
    """Synthesize the plain text with TTS and send a voice reply if possible."""

    plain_value = (plain_text or "").strip()
    if not plain_value:
        return

    try:
        audio_bytes = await asyncio.to_thread(tts.synthesize, plain_value)
    except Exception as exc:  # noqa: BLE001 - explicit logging and fallback are required
        await notify_voice_unavailable(
            message,
            logger=logger,
            context=context,
            user_reason="возникла ошибка синтеза речи",
            technical_reason="TTS synthesis raised an exception",
            exc=exc,
        )
        return

    if not audio_bytes:
        await notify_voice_unavailable(
            message,
            logger=logger,
            context=context,
            user_reason="сервис озвучки вернул пустой ответ",
            technical_reason="TTS service returned empty audio",
        )
        return

    audio = types.BufferedInputFile(audio_bytes, filename=audio_filename)
    try:
        await message.answer_audio(audio)
    except Exception:  # noqa: BLE001 - the calling context logs the failure
        logger.exception("Failed to send voice message for %s", context)
