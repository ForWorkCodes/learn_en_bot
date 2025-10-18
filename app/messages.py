from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from .markdown import bold, escape, italic


@dataclass(frozen=True)
class FormattedMessage:
    markdown: str
    plain: str


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


def _prepare_assignment_details(
    *, explanation: str, examples_json: str
) -> tuple[str, str, str | None]:
    try:
        examples_raw = json.loads(examples_json) if examples_json else []
    except Exception:
        examples_raw = []

    examples = list(_iter_examples(examples_raw))
    example_text, example_translation = (examples[0] if examples else ("", None))

    explanation_value = explanation.strip()
    if "\n" in explanation_value:
        explanation_value = " ".join(
            part.strip() for part in explanation_value.splitlines() if part.strip()
        )

    return explanation_value, example_text, example_translation


def format_assignment_message(
    *, verb: str, translation: str, explanation: str, examples_json: str
) -> FormattedMessage:
    explanation_value, example_text, example_translation = _prepare_assignment_details(
        explanation=explanation, examples_json=examples_json
    )

    markdown_parts: list[str] = [
        f"{bold('Фразовый глагол дня')}: {escape(verb)} — {escape(translation)}",
        italic(explanation_value),
    ]
    plain_parts: list[str] = [
        f"Фразовый глагол дня: {verb} — {translation}",
        explanation_value,
    ]

    if example_text:
        markdown_parts.append(f"{bold('Пример')}: {escape(example_text)}")
        plain_parts.append(f"Пример: {example_text}")
        translation_value = (
            example_translation
            or "Попробуй перевести это предложение самостоятельно."
        )
        markdown_parts.append(f"{bold('Перевод')}: {escape(translation_value)}")
        plain_parts.append(f"Перевод: {translation_value}")
    else:
        markdown_parts.append(
            f"{bold('Пример')}: {escape('Попробуй составить короткое предложение с этим глаголом.')}"
        )
        plain_parts.append(
            "Пример: Попробуй составить короткое предложение с этим глаголом."
        )
        markdown_parts.append(
            f"{bold('Перевод')}: {escape('Затем переведи его на русский язык самостоятельно.')}"
        )
        plain_parts.append(
            "Перевод: Затем переведи его на русский язык самостоятельно."
        )

    markdown_parts.append(escape("Напиши своё короткое предложение — я подскажу, всё ли верно."))
    plain_parts.append("Напиши своё короткое предложение — я подскажу, всё ли верно.")
    return FormattedMessage("\n\n".join(markdown_parts), "\n\n".join(plain_parts))


def format_assignment_reminder(
    *, verb: str, translation: str, explanation: str, examples_json: str
) -> FormattedMessage:
    explanation_value, example_text, example_translation = _prepare_assignment_details(
        explanation=explanation, examples_json=examples_json
    )

    markdown_parts: list[str] = [
        f"{bold('Фразовый глагол дня')}: {escape(verb)} — {escape(translation)}",
        f"{bold('Объяснение')}: {escape(explanation_value)}",
    ]
    plain_parts: list[str] = [
        f"Фразовый глагол дня: {verb} — {translation}",
        f"Объяснение: {explanation_value}",
    ]

    if example_text:
        markdown_parts.append(f"{bold('Пример')}: {escape(example_text)}")
        plain_parts.append(f"Пример: {example_text}")
        if example_translation:
            markdown_parts.append(f"{bold('Перевод')}: {escape(example_translation)}")
            plain_parts.append(f"Перевод: {example_translation}")
        else:
            markdown_parts.append(
                f"{bold('Перевод')}: {escape('Попробуй перевести это предложение самостоятельно.')}"
            )
            plain_parts.append(
                "Перевод: Попробуй перевести это предложение самостоятельно."
            )
    else:
        markdown_parts.append(
            f"{bold('Пример')}: {escape('Попробуй составить короткое предложение с этим глаголом.')}"
        )
        plain_parts.append(
            "Пример: Попробуй составить короткое предложение с этим глаголом."
        )

    return FormattedMessage("\n\n".join(markdown_parts), "\n\n".join(plain_parts))

