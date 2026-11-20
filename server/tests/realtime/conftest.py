"""Socket tests leave no rows behind (same fixture as ``tests/events``)."""

from tests.events.conftest import _leave_database_empty

__all__ = ["_leave_database_empty"]
