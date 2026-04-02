"""Database initialization helpers."""

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from loguru import logger

from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import engine
from app.models.user import User


def _ensure_runtime_schema() -> None:
    """Apply lightweight additive schema updates for SQLite deployments."""
    inspector = inspect(engine)
    if "conversation_turns" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"] for column in inspector.get_columns("conversation_turns")
    }
    required_columns = {
        "sources_json": "TEXT",
        "memory_json": "TEXT",
    }

    with engine.begin() as connection:
        for column_name, column_type in required_columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(
                text(
                    f"ALTER TABLE conversation_turns ADD COLUMN {column_name} {column_type}"
                )
            )
            logger.info(f"Added runtime column conversation_turns.{column_name}")


def init_db(db: Session) -> None:
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)
    _ensure_runtime_schema()
    logger.info("Database tables created.")


def create_first_superuser(
    db: Session,
    username: str = "admin",
    password: str = "admin123",
    email: str = "admin@example.com",
) -> User:
    """Create the first superuser if it does not exist."""
    user = db.query(User).filter(User.username == username).first()
    if user:
        logger.info(f"Superuser already exists: {username}")
        return user

    user = User(
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        full_name="System Administrator",
        is_active=True,
        is_superuser=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"Created superuser: {username}")
    return user
