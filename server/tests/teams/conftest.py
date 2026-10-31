"""Teams tests leave no rows behind: ``tests/test_migrations.py`` assumes an empty database."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text

from tests.helpers import TEST_DB_URL


@pytest.fixture(autouse=True)
def _leave_database_empty(clean: None) -> Iterator[None]:
    yield
    assert TEST_DB_URL
    engine = create_engine(TEST_DB_URL)
    try:
        with engine.begin() as conn:
            conn.execute(text('TRUNCATE team, season, "user" RESTART IDENTITY CASCADE'))
    finally:
        engine.dispose()
