from __future__ import annotations

import json


def format_assignment_message(*, verb: str, translation: str, explanation: str, examples_json: str) -> str:
    try:
        examples = json.loads(examples_json) if examples_json else []
    except Exception:
        examples = []

    example_text = ""
    for item in examples:
        if isinstance(item, str) and item.strip():
            example_text = item.strip()
            break

    lines: list[str] = [
        f"Глагол: {verb} — {translation}",
        f"Объяснение: {explanation.strip()}",
    ]

    if example_text:
        lines.append(f"Пример: {example_text}")
    else:
        lines.append("Пример: скоро добавлю подходящее предложение.")

    lines.append("")
    lines.append("Составь своё предложение с этим глаголом — я помогу его проверить.")
    return "\n".join(lines)
