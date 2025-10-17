from contextlib import contextmanager
from typing import Iterator, List, Optional
from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session

from .models import Base, User, Assignment


class Database:
    def __init__(self, url: str):
        # echo=False чтобы не захламлять вывод; можно поставить True для отладки
        self.engine = create_engine(url, echo=False, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, class_=Session, future=True)

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine)

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
                return user
            user = User(chat_id=chat_id, username=username)
            db.add(user)
            db.flush()
            return user

    def list_users(self) -> List[User]:
        with self.session() as db:
            return list(db.scalars(select(User)).all())

    # --- assignments ---
    def get_today_assignment(self, user_id: int) -> Optional[Assignment]:
        with self.session() as db:
            return db.scalar(
                select(Assignment).where(Assignment.user_id == user_id, Assignment.date_assigned == date.today())
            )

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
            )
            db.add(assgn)
            db.flush()
            return assgn

    def ensure_today_assignment(self, user: User, *, verb: str, translation: str, explanation: str, examples_json: str) -> Assignment:
        with self.session() as db:
            assgn = db.scalar(
                select(Assignment).where(Assignment.user_id == user.id, Assignment.date_assigned == date.today())
            )
            if assgn:
                return assgn
            assgn = Assignment(
                user_id=user.id,
                date_assigned=date.today(),
                phrasal_verb=verb,
                translation=translation,
                explanation=explanation,
                examples_json=examples_json,
                status="assigned",
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
