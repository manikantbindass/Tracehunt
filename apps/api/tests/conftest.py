"""Every test uses a new SQLite file; never touch a developer's workspace database."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

os.environ.update(
    DATABASE_URL="sqlite://",
    DEMO_MODE="true",
    SEED_DEMO="false",
    RUN_WORKER="false",
    REDIS_URL="",
    OPENAI_API_KEY="",
    ALERT_WEBHOOK_URL="",
    MONITOR_ALLOW_PRIVATE_NETWORKS="false",
)

from app import main, worker  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import get_db  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def pragmas(connection, _):
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")

    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessions)
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    monkeypatch.setattr(worker, "engine", engine)
    yield sessions
    engine.dispose()


@pytest.fixture
def db(database):
    with database() as session:
        yield session


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def client(database):
    def override_db():
        with database() as session:
            yield session

    main.app.dependency_overrides[get_db] = override_db
    with TestClient(main.app) as client:
        yield client
    main.app.dependency_overrides.clear()
