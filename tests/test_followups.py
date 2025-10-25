import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytz

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import DueFollowup
from app.scheduler import LessonScheduler


class DummyDb:
    def __init__(self):
        self.scheduled = None
        self.cleared = []
        self.due_followups = []
        self.marked = []
        self.removed = []
        self.postponed = []

    # Scheduling helpers
    def schedule_followups(self, assignment_id: int, followups):
        self.scheduled = (assignment_id, list(followups))

    def clear_followups(self, assignment_id: int):
        self.cleared.append(assignment_id)

    # Follow-up processing helpers
    def list_due_followups(self, now_utc: datetime):
        return list(self.due_followups)

    def mark_followup_sent(self, assignment_id: int, which: int):
        self.marked.append((assignment_id, which))

    def remove_followup(self, followup_id: int):
        self.removed.append(followup_id)

    def postpone_followup(self, followup_id: int, new_run_at: datetime):
        self.postponed.append((followup_id, new_run_at))

    # Assignment helpers used by _send_followup
    def get_user_by_id(self, user_id: int):
        raise AssertionError("Unexpected call")

    def get_today_assignment(self, user_id: int):
        raise AssertionError("Unexpected call")

    def get_assignment_by_id(self, assignment_id: int):
        raise AssertionError("Unexpected call")


@pytest.fixture(autouse=True)
def patch_to_thread(monkeypatch):
    async def immediate(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", immediate)


def freeze_datetime(monkeypatch, when: datetime, module):
    aware_when = when

    class FrozenDateTime(datetime):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return aware_when
            if hasattr(tz, "normalize"):
                return tz.normalize(aware_when.astimezone(tz))
            return aware_when.astimezone(tz)

        @classmethod
        def utcnow(cls):
            return aware_when.astimezone(pytz.UTC).replace(tzinfo=None)

    monkeypatch.setattr(module, "datetime", FrozenDateTime)


def test_plan_followups_two_slots(monkeypatch):
    from app import scheduler as scheduler_module

    tz_name = "Europe/Moscow"
    tz = pytz.timezone(tz_name)
    base_local = tz.localize(datetime(2025, 10, 25, 9, 30))
    freeze_datetime(monkeypatch, base_local, scheduler_module)

    db = DummyDb()
    scheduler = LessonScheduler(
        bot=AsyncMock(),
        db=db,
        gemini=MagicMock(),
        tts=MagicMock(),
        default_cron="0 0 * * *",
        timezone=tz_name,
    )

    asyncio.run(scheduler.plan_followups(user_id=1, assignment_id=42))

    assert db.scheduled is not None
    assignment_id, followups = db.scheduled
    assert assignment_id == 42
    assert followups == [
        (
            1,
            tz.localize(datetime(2025, 10, 25, 11, 30))
            .astimezone(pytz.UTC)
            .replace(tzinfo=None),
        ),
        (
            2,
            tz.localize(datetime(2025, 10, 25, 16, 30))
            .astimezone(pytz.UTC)
            .replace(tzinfo=None),
        ),
    ]
    assert db.cleared == []


def test_plan_followups_single_slot_near_window_end(monkeypatch):
    from app import scheduler as scheduler_module

    tz_name = "Europe/Moscow"
    tz = pytz.timezone(tz_name)
    base_local = tz.localize(datetime(2025, 10, 25, 22, 50))
    freeze_datetime(monkeypatch, base_local, scheduler_module)

    db = DummyDb()
    scheduler = LessonScheduler(
        bot=AsyncMock(),
        db=db,
        gemini=MagicMock(),
        tts=MagicMock(),
        default_cron="0 0 * * *",
        timezone=tz_name,
    )

    asyncio.run(scheduler.plan_followups(user_id=1, assignment_id=99))

    assert db.scheduled is not None
    assignment_id, followups = db.scheduled
    assert assignment_id == 99
    assert followups == [
        (
            1,
            tz.localize(datetime(2025, 10, 25, 23, 0))
            .astimezone(pytz.UTC)
            .replace(tzinfo=None),
        ),
    ]
    assert db.cleared == []


def test_plan_followups_clears_when_no_time_left(monkeypatch):
    from app import scheduler as scheduler_module

    tz_name = "Europe/Moscow"
    tz = pytz.timezone(tz_name)
    base_local = tz.localize(datetime(2025, 10, 25, 23, 55))
    freeze_datetime(monkeypatch, base_local, scheduler_module)

    db = DummyDb()
    scheduler = LessonScheduler(
        bot=AsyncMock(),
        db=db,
        gemini=MagicMock(),
        tts=MagicMock(),
        default_cron="0 0 * * *",
        timezone=tz_name,
    )

    asyncio.run(scheduler.plan_followups(user_id=1, assignment_id=7))

    assert db.scheduled is None
    assert db.cleared == [7]


def test_send_followup_uses_assignment_lookup_by_id(monkeypatch):
    user = SimpleNamespace(id=10, chat_id=100, is_subscribed=True)
    yesterday_assignment = SimpleNamespace(
        id=55,
        user_id=10,
        phrasal_verb="check",
        status="assigned",
        followup1_sent=False,
        followup2_sent=False,
    )
    today_assignment = SimpleNamespace(
        id=99,
        user_id=10,
        phrasal_verb="today",
        status="assigned",
        followup1_sent=False,
        followup2_sent=False,
    )

    class FollowupDb(DummyDb):
        def get_user_by_id(self, user_id: int):
            assert user_id == user.id
            return user

        def get_today_assignment(self, user_id: int):
            return today_assignment

        def get_assignment_by_id(self, assignment_id: int):
            if assignment_id == yesterday_assignment.id:
                return yesterday_assignment
            return None

    scheduler = LessonScheduler(
        bot=AsyncMock(),
        db=FollowupDb(),
        gemini=MagicMock(),
        tts=MagicMock(),
        default_cron="0 0 * * *",
        timezone="UTC",
    )
    scheduler.bot.send_message = AsyncMock(return_value=None)

    result = asyncio.run(
        scheduler._send_followup(user_id=10, assignment_id=55, which=1)
    )

    assert result == "sent"
    scheduler.bot.send_message.assert_awaited()

def test_process_followups_sent_flow(monkeypatch):
    from app import scheduler as scheduler_module

    base_utc = pytz.UTC.localize(datetime(2025, 10, 25, 12, 0))
    freeze_datetime(monkeypatch, base_utc, scheduler_module)

    db = DummyDb()
    db.due_followups = [
        DueFollowup(
            id=1,
            assignment_id=55,
            user_id=10,
            chat_id=100,
            which=1,
            run_at=base_utc.replace(tzinfo=None),
        )
    ]

    scheduler = LessonScheduler(
        bot=AsyncMock(),
        db=db,
        gemini=MagicMock(),
        tts=MagicMock(),
        default_cron="0 0 * * *",
        timezone="UTC",
    )

    async def fake_send_followup(user_id, assignment_id, which):
        assert (user_id, assignment_id, which) == (10, 55, 1)
        return "sent"

    monkeypatch.setattr(scheduler, "_send_followup", fake_send_followup)

    asyncio.run(scheduler._process_followups())

    assert db.marked == [(55, 1)]
    assert db.removed == [1]
    assert db.postponed == []


def test_process_followups_retry_flow(monkeypatch):
    from app import scheduler as scheduler_module

    base_utc = pytz.UTC.localize(datetime(2025, 10, 25, 12, 0))
    freeze_datetime(monkeypatch, base_utc, scheduler_module)

    db = DummyDb()
    db.due_followups = [
        DueFollowup(
            id=2,
            assignment_id=77,
            user_id=11,
            chat_id=200,
            which=2,
            run_at=base_utc.replace(tzinfo=None),
        )
    ]

    scheduler = LessonScheduler(
        bot=AsyncMock(),
        db=db,
        gemini=MagicMock(),
        tts=MagicMock(),
        default_cron="0 0 * * *",
        timezone="UTC",
    )

    async def fake_send_followup(user_id, assignment_id, which):
        return "retry"

    monkeypatch.setattr(scheduler, "_send_followup", fake_send_followup)

    asyncio.run(scheduler._process_followups())

    assert db.marked == []
    assert db.removed == []
    assert len(db.postponed) == 1
    followup_id, new_run_at = db.postponed[0]
    assert followup_id == 2
    assert new_run_at == base_utc.replace(tzinfo=None) + timedelta(minutes=15)


def test_process_followups_skip_flow(monkeypatch):
    from app import scheduler as scheduler_module

    base_utc = pytz.UTC.localize(datetime(2025, 10, 25, 12, 0))
    freeze_datetime(monkeypatch, base_utc, scheduler_module)

    db = DummyDb()
    db.due_followups = [
        DueFollowup(
            id=3,
            assignment_id=88,
            user_id=12,
            chat_id=300,
            which=1,
            run_at=base_utc.replace(tzinfo=None),
        )
    ]

    scheduler = LessonScheduler(
        bot=AsyncMock(),
        db=db,
        gemini=MagicMock(),
        tts=MagicMock(),
        default_cron="0 0 * * *",
        timezone="UTC",
    )

    async def fake_send_followup(user_id, assignment_id, which):
        return "skip"

    monkeypatch.setattr(scheduler, "_send_followup", fake_send_followup)

    asyncio.run(scheduler._process_followups())

    assert db.marked == []
    assert db.removed == [3]
    assert db.postponed == []
