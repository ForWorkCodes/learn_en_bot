from contextlib import contextmanager
from typing import Iterator, List, Optional
from datetime import date, datetime
import logging

from sqlalchemy import create_engine, select, text, inspect
from sqlalchemy.orm import sessionmaker, Session

from .models import Base, User, Assignment


logger = logging.getLogger("learn_en_bot.db")


class Database:
    def __init__(self, url: str):
        # echo=False чтобы не захламлять вывод; можно поставить True для отладки
        self.engine = create_engine(url, echo=False, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, class_=Session, future=True)

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine)
        try:
            with self.engine.begin() as conn:
                inspector = inspect(conn)

                assignment_columns = {
                    column["name"] for column in inspector.get_columns("assignments")
                }
                if "delivered_at" not in assignment_columns:
                    conn.execute(
                        text("ALTER TABLE assignments ADD COLUMN delivered_at TIMESTAMP NULL")
                    )
                    conn.execute(
                        text("UPDATE assignments SET delivered_at = CURRENT_TIMESTAMP")
                    )

                user_columns = {column["name"] for column in inspector.get_columns("users")}
                if "send_audio" not in user_columns:
                    conn.execute(
                        text(
                            "ALTER TABLE users "
                            "ADD COLUMN send_audio BOOLEAN NOT NULL DEFAULT TRUE"
                        )
                    )
                if "is_subscribed" not in user_columns:
                    conn.execute(
                        text(
                            "ALTER TABLE users "
                            "ADD COLUMN is_subscribed BOOLEAN NOT NULL DEFAULT TRUE"
                        )
                    )
        except Exception:
            logger.exception("Failed to ensure database schema is up to date")

    @contextmanager
    def session(self) -> Iterator[Session]:
        db = self.SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # --- helpers ---
    def add_or_get_user(self, chat_id: int, username: str | None) -> User:
        with self.session() as db:
            user = db.scalar(select(User).where(User.chat_id == chat_id))
            if user:
                if username and user.username != username:
                    user.username = username
                return user
            user = User(chat_id=chat_id, username=username)
            db.add(user)
            db.flush()
            return user

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        with self.session() as db:
            return db.get(User, user_id)

    def get_user_by_chat(self, chat_id: int) -> Optional[User]:
        with self.session() as db:
            return db.scalar(select(User).where(User.chat_id == chat_id))

    def update_user_daily_time(
        self,
        user_id: int,
        hour: int | None,
        minute: int | None,
        *,
        mark_subscribed: bool | None = None,
    ) -> None:
        with self.session() as db:
            user = db.get(User, user_id)
            if not user:
                return
            user.daily_hour = hour
            user.daily_minute = minute
            if mark_subscribed is not None:
                user.is_subscribed = mark_subscribed

    def update_user_subscription(self, user_id: int, subscribed: bool) -> None:
        with self.session() as db:
            user = db.get(User, user_id)
            if not user:
                return
            user.is_subscribed = subscribed

    def update_user_audio_preference(self, user_id: int, send_audio: bool) -> None:
        with self.session() as db:
            user = db.get(User, user_id)
            if not user:
                return
            user.send_audio = send_audio

    def list_users(self) -> List[User]:
        with self.session() as db:
            return list(db.scalars(select(User)).all())

    def list_users_without_daily_time(self) -> List[User]:
        with self.session() as db:
            return list(
                db.scalars(
                    select(User).where(
                        (User.daily_hour.is_(None) | User.daily_minute.is_(None))
                        & (User.is_subscribed.is_(True))
                    )
                ).all()
            )

    # --- assignments ---
    def get_assignment_by_id(self, assignment_id: int) -> Optional[Assignment]:
        with self.session() as db:
            return db.get(Assignment, assignment_id)

    def get_today_assignment(self, user_id: int) -> Optional[Assignment]:
        with self.session() as db:
            return db.scalar(
                select(Assignment).where(Assignment.user_id == user_id, Assignment.date_assigned == date.today())
            )

    def get_latest_assignment(self, user_id: int) -> Optional[Assignment]:
        with self.session() as db:
            stmt = (
                select(Assignment)
                .where(Assignment.user_id == user_id)
                .order_by(Assignment.date_assigned.desc(), Assignment.created_at.desc())
            )
            return db.scalars(stmt).first()

    def get_today_assignment_by_chat(self, chat_id: int) -> Optional[Assignment]:
        with self.session() as db:
            user = db.scalar(select(User).where(User.chat_id == chat_id))
            if not user:
                return None
            return db.scalar(
                select(Assignment).where(Assignment.user_id == user.id, Assignment.date_assigned == date.today())
            )

    def create_today_assignment(self, user_id: int, *, verb: str, translation: str, explanation: str, examples_json: str) -> Assignment:
        with self.session() as db:
            assgn = Assignment(
                user_id=user_id,
                date_assigned=date.today(),
                phrasal_verb=verb,
                translation=translation,
                explanation=explanation,
                examples_json=examples_json,
                status="assigned",
                delivered_at=None,
            )
            db.add(assgn)
            db.flush()
            return assgn

    def ensure_today_assignment(
        self,
        user: User,
        *,
        verb: str,
        translation: str,
        explanation: str,
        examples_json: str,
        force_new: bool = False,
    ) -> Assignment:
        with self.session() as db:
            assgn = db.scalar(
                select(Assignment).where(Assignment.user_id == user.id, Assignment.date_assigned == date.today())
            )
            if assgn and not force_new:
                return assgn
            if assgn and force_new:
                assgn.phrasal_verb = verb
                assgn.translation = translation
                assgn.explanation = explanation
                assgn.examples_json = examples_json
                assgn.status = "assigned"
                assgn.followup1_sent = False
                assgn.followup2_sent = False
                assgn.delivered_at = None
                return assgn
            assgn = Assignment(
                user_id=user.id,
                date_assigned=date.today(),
                phrasal_verb=verb,
                translation=translation,
                explanation=explanation,
                examples_json=examples_json,
                status="assigned",
                delivered_at=None,
            )
            db.add(assgn)
            db.flush()
            return assgn

    def mark_mastered(self, assignment_id: int) -> None:
        with self.session() as db:
            assgn = db.get(Assignment, assignment_id)
            if assgn:
                assgn.status = "mastered"

    def mark_followup_sent(self, assignment_id: int, which: int) -> None:
        with self.session() as db:
            assgn = db.get(Assignment, assignment_id)
            if not assgn:
                return
            if which == 1:
                assgn.followup1_sent = True
            elif which == 2:
                assgn.followup2_sent = True

    def mark_assignment_delivered(self, assignment_id: int, delivered_at: datetime | None = None) -> None:
        with self.session() as db:
            assgn = db.get(Assignment, assignment_id)
            if assgn:
                assgn.delivered_at = delivered_at or datetime.utcnow()

    def list_undelivered_assignments(self) -> List[Assignment]:
        with self.session() as db:
            return list(
                db.scalars(select(Assignment).where(Assignment.delivered_at.is_(None))).all()
            )
