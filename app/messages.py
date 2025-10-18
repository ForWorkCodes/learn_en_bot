from __future__ import annotations

import json
from typing import Any, Iterable

from .markdown import bold, escape, italic


def _iter_examples(raw: Iterable[Any]) -> Iterable[tuple[str, str | None]]:
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if text:
                yield text, None
        elif isinstance(item, dict):
            english_keys = ("text", "sentence", "example", "english")
            translation_keys = ("translation", "meaning", "russian", "ru")
            text_value = next((str(item[k]).strip() for k in english_keys if item.get(k)), "")
            translation_value = next(
                (str(item[k]).strip() for k in translation_keys if item.get(k)),
                "",
            )
            if text_value:
                yield text_value, translation_value or None


def format_assignment_message(*, verb: str, translation: str, explanation: str, examples_json: str) -> str:
    try:
        examples_raw = json.loads(examples_json) if examples_json else []
    except Exception:
        examples_raw = []

    examples = list(_iter_examples(examples_raw))
    example_text, example_translation = (examples[0] if examples else ("", None))

    parts: list[str] = [
        f"{bold('Фразовый глагол дня')}: {escape(verb)} — {escape(translation)}",
        italic(explanation.strip()),
    ]

    if example_text:
        parts.append(f"{bold('Пример')}: {escape(example_text)}")
        translation_value = (
            example_translation
            or "Попробуй перевести это предложение самостоятельно."
        )
        parts.append(f"{bold('Перевод')}: {escape(translation_value)}")
    else:
        parts.append(
            f"{bold('Пример')}: {escape('Попробуй составить короткое предложение с этим глаголом.')}"
        )
        parts.append(
            f"{bold('Перевод')}: {escape('Затем переведи его на русский язык самостоятельно.')}"
        )

    parts.append(escape("Напиши своё короткое предложение — я подскажу, всё ли верно."))
    return "\n\n".join(parts)

