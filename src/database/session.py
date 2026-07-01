"""
Engine/session setup for the MAHARERA warehouse. Reads DATABASE_URL from .env.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.database.models import Base

load_dotenv()

_DATABASE_URL = os.environ.get("DATABASE_URL")


def get_engine() -> Engine:
    if not _DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set — check .env")
    return create_engine(_DATABASE_URL, pool_pre_ping=True)


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    engine = engine or get_engine()
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine | None = None) -> Engine:
    """Create all tables if they don't already exist."""
    engine = engine or get_engine()
    Base.metadata.create_all(engine)
    return engine
