from __future__ import annotations

import os

os.environ.setdefault("ENV", "test")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/communityapp_test",
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.core.db import Base
from backend.core.dependencies import get_db
from backend.security.auth import get_auth_db
from backend.main import app
from backend.models import Community

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, future=True)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    _reset_db()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def clean_db():
    """Delete all rows between tests without dropping tables."""
    yield
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM auth_failed_login_attempts"))
        conn.execute(text("DELETE FROM refresh_tokens"))
        conn.execute(text("DELETE FROM posts"))
        conn.execute(text("DELETE FROM follows"))
        conn.execute(text("DELETE FROM friendships"))
        conn.execute(text("DELETE FROM users"))
        conn.execute(text("DELETE FROM communities"))
        conn.commit()


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_auth_db] = override_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def default_community(db):
    c = Community(id="community-default", name="Default Community")
    db.add(c)
    db.commit()
    return c
