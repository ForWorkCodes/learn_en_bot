from __future__ import annotations

import json
import html


def format_assignment_message(*, verb: str, translation: str, explanation: str, examples_json: str) -> str:
    try:
        examples = json.loads(examples_json) if examples_json else []
    except Exception:
        examples = []

    v = html.escape(verb)
    tr = html.escape(translation)
    ex_text = html.escape(explanation.strip())

    example_text = ""
    for item in examples:
        if isinstance(item, str) and item.strip():
            example_text = html.escape(item.strip())
            break

    parts: list[str] = [
        f"<b>Фразовый глагол дня:</b> {v} — {tr}",
        f"<i>{ex_text}</i>",
    ]

    if example_text:
        parts.append(f"<b>Пример:</b> {example_text}")
    else:
        parts.append("<b>Пример:</b> попробуй составить короткое предложение с этим глаголом.")

    parts.append("")
    parts.append("Напиши своё короткое предложение — я подскажу, всё ли верно.")
    return "\n".join(parts)

