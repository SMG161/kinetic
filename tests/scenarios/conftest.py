"""Scenario tests go through the HTTP API against a real Postgres database.

They use their own database, kinetic_test, on the same server as the dev database:
created if missing and migrated once per run, then emptied before every test.
Time is a FixedClock, so each test decides what "now" is.
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import make_url

from kinetic import db
from kinetic.dependencies import get_clock
from kinetic.main import create_app
from kinetic.settings import get_settings
from kinetic.shared_kernel import FixedClock

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
TEST_DATABASE = "kinetic_test"
CONTEXT_SCHEMAS = ["identity", "directory", "care_team", "records"]
ALEMBIC_INI = Path(__file__).parents[2] / "alembic.ini"


@pytest.fixture(scope="session", autouse=True)
def test_database() -> None:
    url = make_url(get_settings().database_url).set(database=TEST_DATABASE)
    _create_database_if_missing(url)
    # Point the whole app (and Alembic) at the test database for this run.
    os.environ["KINETIC_DATABASE_URL"] = url.render_as_string(hide_password=False)
    get_settings.cache_clear()
    db.get_engine.cache_clear()
    db.get_session_factory.cache_clear()
    command.upgrade(Config(ALEMBIC_INI), "head")


@pytest.fixture(autouse=True)
def empty_tables(test_database: None) -> None:
    with db.get_engine().begin() as conn:
        tables = conn.scalars(
            text("SELECT format('%I.%I', schemaname, tablename) FROM pg_tables WHERE schemaname = ANY(:schemas)"),
            {"schemas": CONTEXT_SCHEMAS},
        ).all()
        if tables:
            conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(T0)


@pytest.fixture
def client(clock: FixedClock) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_clock] = lambda: clock
    with TestClient(app) as test_client:
        yield test_client


def _create_database_if_missing(url: URL) -> None:
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()
