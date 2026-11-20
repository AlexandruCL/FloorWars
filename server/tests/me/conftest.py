"""Read-endpoint tests leave no rows behind (``tests/test_migrations.py`` needs an empty DB)."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text

from tests.helpers import TEST_DB_URL


@pytest.fixture(autouse=True)
def _leave_database_empty(request: pytest.FixtureRequest) -> Iterator[None]:
    # Only for tests that use the database (the fake-client unit tests do not).
    if "client" not in request.fixturenames and "make_app" not in request.fixturenames:
        yield
        return
    yield
    assert TEST_DB_URL
    engine = create_engine(TEST_DB_URL)
    try:
        with engine.begin() as conn:
            conn.execute(text('TRUNCATE building, team, season, "user" RESTART IDENTITY CASCADE'))
    finally:
        engine.dispose()
