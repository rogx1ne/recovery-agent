"""
db.py — SQLAlchemy engine, session factory, and Base for declarative models.
Uses SQLite by default (DATABASE_URL from .env).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

# connect_args is required for SQLite to allow multi-threaded access from FastAPI
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=(settings.app_env == "development"),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""
    pass


def get_db():
    """
    FastAPI dependency that provides a database session per request,
    and ensures it is closed after the response is sent.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables defined by models that import Base."""
    # Import models here so SQLAlchemy registers them before create_all
    from app.models import transaction, audit_log  # noqa: F401
    Base.metadata.create_all(bind=engine)
