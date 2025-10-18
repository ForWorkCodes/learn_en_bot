from __future__ import annotations

import asyncio
import json
from typing import Tuple

from ..db import Database
from ..gemini import GeminiClient
from ..messages import format_assignment_message
from ..models import Assignment, User


async def ensure_daily_assignment(
    db: Database,
    gemini: GeminiClient,
    user: User,
    *,
    force_new: bool = False,
) -> Tuple[Assignment, str, bool]:
    existing = await asyncio.to_thread(db.get_today_assignment, user.id)
    if existing and not force_new:
        message = format_assignment_message(
            verb=existing.phrasal_verb,
            translation=existing.translation,
            explanation=existing.explanation,
            examples_json=existing.examples_json,
        )
        return existing, message, False

    data = await asyncio.to_thread(gemini.generate_phrasal_verb)
    examples_json = json.dumps(data.get("examples", []), ensure_ascii=False)
    assignment = await asyncio.to_thread(
        db.ensure_today_assignment,
        user,
        verb=data["verb"],
        translation=data["translation"],
        explanation=data["explanation"],
        examples_json=examples_json,
        force_new=force_new,
    )
    message = format_assignment_message(
        verb=assignment.phrasal_verb,
        translation=assignment.translation,
        explanation=assignment.explanation,
        examples_json=assignment.examples_json,
    )
    created = force_new or existing is None
    return assignment, message, created
