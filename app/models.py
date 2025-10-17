from datetime import datetime, date
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, DateTime, Date, ForeignKey, Boolean, Text


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    daily_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"User(id={self.id}, chat_id={self.chat_id}, username={self.username})"


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date_assigned: Mapped[date] = mapped_column(Date, index=True)

    phrasal_verb: Mapped[str] = mapped_column(String(128))
    translation: Mapped[str] = mapped_column(String(255))
    explanation: Mapped[str] = mapped_column(Text)
    examples_json: Mapped[str] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(32), default="assigned")  # assigned|mastered
    followup1_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    followup2_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(backref="assignments")
