"""Monthly partitions of ``climb_segment`` (``climb_segment_YYYYMM``, months in UTC).

There is no default partition, so an insert outside the existing months fails. This must run
before the months run out, with the migrator role (the app role has no DDL)::

    python -m app.segments.partitions

TODO(Week 5): schedule it with Celery beat. Until then the CLI has to be run by hand.
"""

from datetime import UTC, datetime

from sqlalchemy import Connection, create_engine, text

from app.db.session import database_url


def _month_start(year: int, month_index: int) -> datetime:
    """UTC start of the month ``month_index`` months after January of ``year`` (may be negative)."""
    years, month = divmod(month_index, 12)
    return datetime(year + years, month + 1, 1, tzinfo=UTC)


def ensure_partitions(
    conn: Connection, months_ahead: int = 2, now: datetime | None = None
) -> list[str]:
    """Create the partitions of the previous month to ``months_ahead`` after this one.

    Idempotent. The previous month is included because a segment may start up to 7 days before
    it is received, which can fall in the month before. Returns the names of all the partitions
    in that range. The caller commits.
    """
    if months_ahead < 0:
        raise ValueError("months_ahead must not be negative")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    first = current.month - 1
    names = []
    for index in range(first - 1, first + months_ahead + 1):
        start, end = _month_start(current.year, index), _month_start(current.year, index + 1)
        name = f"climb_segment_{start:%Y%m}"
        # Name and bounds come from the dates above; DDL takes no bound parameters. Qualified
        # because infra/sql/roles.sql puts pg_catalog first in the superuser's search_path.
        conn.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS public.{name} PARTITION OF public.climb_segment "
                f"FOR VALUES FROM ('{start:%Y-%m-%d} 00:00:00+00') "
                f"TO ('{end:%Y-%m-%d} 00:00:00+00')"
            )
        )
        names.append(name)
    return names


def main() -> None:
    engine = create_engine(database_url())
    try:
        with engine.begin() as conn:
            names = ensure_partitions(conn)
    finally:
        engine.dispose()
    print(f"partitions present: {', '.join(names)}")


if __name__ == "__main__":
    main()
