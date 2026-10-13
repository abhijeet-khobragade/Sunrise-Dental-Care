"""Database models: appointments booked by the bot, and hand-offs to human staff."""

from datetime import datetime

from sqlalchemy import String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


class Appointment(Base):
    __tablename__ = "appointments"
    # One appointment per time slot - the database itself blocks double booking.
    __table_args__ = (UniqueConstraint("date", "time", name="uq_slot"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    service: Mapped[str] = mapped_column(String(100))
    date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    time: Mapped[str] = mapped_column(String(5))  # HH:MM
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class Handoff(Base):
    __tablename__ = "handoffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64))
    contact: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


def make_session_factory(url: str = DATABASE_URL, **engine_kwargs) -> sessionmaker:
    """Create the tables (if missing) and return a factory for DB sessions."""
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, **engine_kwargs)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
