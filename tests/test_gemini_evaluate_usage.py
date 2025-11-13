from unittest.mock import MagicMock

import pytest

from app.gemini import GeminiClient


@pytest.fixture
def client():
    instance = GeminiClient(api_key="")
    return instance


def test_evaluate_usage_prefers_plain_text(client):
    client.generate = MagicMock(
        return_value="Feedback: Отличная работа!\nScore: 5/5"
    )

    feedback, mastered = client.evaluate_usage("pick up", "I picked up the book.")

    assert feedback == "Отличная работа!"
    assert mastered is True


def test_evaluate_usage_falls_back_to_json(client):
    client.generate = MagicMock(
        return_value='Вот ответ:\n{"feedback": "Добавь больше контекста.", "score": 3}'
    )

    feedback, mastered = client.evaluate_usage("pick up", "I pick book.")

    assert feedback == "Добавь больше контекста."
    assert mastered is False
