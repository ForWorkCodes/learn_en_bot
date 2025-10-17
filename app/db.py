from contextlib import contextmanager
from typing import Iterator, List

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session

from .models import Base, User


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
