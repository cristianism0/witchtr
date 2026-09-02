"""Shared fixtures for the entire test suite.

Uses a single SQLite in-memory database for ALL tests to avoid
the need for a running PostgreSQL instance.
"""

import io
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.database.session as _session_mod
from api.database.models import Base
from api.database.repository import DBJobRepository
from api.database.session import get_db
from api.main import app

# ---------------------------------------------------------------------------
# Single in-memory SQLite engine shared by every test module.
# StaticPool ensures all sessions share the SAME connection (and thus the
# same in-memory database).
# ---------------------------------------------------------------------------
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Patch the production engine so the lifespan's create_all targets SQLite
_session_mod.psql_engine = TEST_ENGINE


@event.listens_for(TEST_ENGINE, "connect")
def _set_sqlite_pragma(dbapi_conn, _connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(bind=TEST_ENGINE, autocommit=False, autoflush=False)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _setup_and_teardown_db():
    """Create tables before each test, drop after."""
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture()
def db_session():
    """Return a fresh DB session for direct repository testing."""
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture()
def repo(db_session):
    """Return a DBJobRepository bound to the test session."""
    return DBJobRepository(db_session)


@pytest.fixture()
def client():
    """Return a TestClient wired to the overridden (SQLite) DB."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_png_bytes(text: str = "hello world", size: tuple[int, int] = (400, 100)) -> bytes:
    img = Image.new("RGB", size, color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), text, fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_file(
    filename: str = "test.png",
    content: bytes | None = None,
    content_type: str = "image/png",
):
    return (filename, content or make_png_bytes(), content_type)


def post_send(client: TestClient, *files):
    return client.post(
        "/send",
        files=[("files", f) for f in files],
    )


def create_job_via_send(client: TestClient, filename: str = "test.png") -> str:
    """Send a file through the API (mocking OCR) and return the job_id."""
    with (
        patch("api.routes.witchtr_router.magic.from_buffer", return_value="image/png"),
        patch("api.routes.witchtr_router.run_job"),
    ):
        res = post_send(client, make_file(filename))
    assert res.status_code == 200
    return res.json()[0]["job_id"]


def make_image_file(path: Path, text: str = "hello world", size: tuple[int, int] = (400, 100)) -> Path:
    """Create a real PNG image with text at the given path."""
    img = Image.new("RGB", size, color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), text, fill=(0, 0, 0))
    img.save(path)
    return path
