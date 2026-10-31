"""Alembic environment.

The URL comes from ``config.attributes["database_url"]`` when set programmatically (tests),
otherwise from settings (``FLOORWARS_DATABASE_URL`` or ``/run/secrets/database_url``).
Migrations run with their own synchronous psycopg engine (``NullPool``); the app uses the sync
engine from ``app/db/session.py``.
"""

from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import create_engine, pool

import app.db.models  # noqa: F401  (registers the tables on the metadata)
from app.db.base import Base
from app.db.session import database_url

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# Objects owned by PostGIS and its companion extensions (the postgis/postgis image also
# installs postgis_topology and postgis_tiger_geocoder). They are not ours; never report them.
POSTGIS_TABLES = frozenset({"spatial_ref_sys", "geometry_columns", "geography_columns"})
POSTGIS_SCHEMAS = frozenset({"tiger", "tiger_data", "topology"})


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    if type_ == "table" and reflected and compare_to is None:
        schema = getattr(obj, "schema", None)
        if name in POSTGIS_TABLES or schema in POSTGIS_SCHEMAS:
            return False
    return True


def _url() -> str:
    url = config.attributes.get("database_url")
    return str(url) if url else database_url()


def _configure(**kwargs: Any) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure(url=_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Pin the schema: the postgis image adds tiger and topology to search_path, and reflection
    # would otherwise see their tables as drift.
    engine = create_engine(
        _url(), poolclass=pool.NullPool, connect_args={"options": "-c search_path=public"}
    )
    with engine.connect() as connection:
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
