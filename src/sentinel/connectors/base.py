"""Turn configured sources into SQLAlchemy engines and table references."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, table, text
from sqlalchemy.exc import ArgumentError, NoSuchModuleError, SQLAlchemyError
from sqlalchemy.sql.expression import TableClause

from sentinel.config.models import Source

_INSTALL_HINTS = {
    "postgres": 'pip install "ninegear-sentinel[postgres]"',
    "snowflake": "Snowflake support arrives in a later release",
    "bigquery": "BigQuery support arrives in a later release",
    "sqlite": "SQLite support is built into Python",
}


class ConnectorError(Exception):
    """A source could not be turned into a working engine."""


def normalise_url(source: Source) -> str:
    """Point plain postgres:// URLs at the psycopg 3 driver Sentinel installs."""
    url = source.url
    if source.type == "postgres":
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


def create_source_engine(name: str, source: Source) -> Engine:
    try:
        return create_engine(normalise_url(source), pool_pre_ping=True)
    except ModuleNotFoundError as exc:
        hint = _INSTALL_HINTS.get(source.type, "")
        raise ConnectorError(
            f"source '{name}': database driver '{exc.name}' is not installed. {hint}".strip()
        ) from None
    except (ArgumentError, NoSuchModuleError) as exc:
        raise ConnectorError(f"source '{name}': invalid connection URL ({exc})") from None


def check_connection(engine: Engine) -> None:
    """Raise SQLAlchemyError if the database can't run a trivial query."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def table_target(name: str) -> TableClause:
    """'analytics.orders' -> a quoted table reference with schema 'analytics'."""
    schema, _, table_name = name.rpartition(".")
    return table(table_name, schema=schema or None)


def short_error(exc: BaseException) -> str:
    """First line of the underlying database error, without SQLAlchemy's wrapping."""
    source = getattr(exc, "orig", None) if isinstance(exc, SQLAlchemyError) else None
    message = str(source if source is not None else exc).strip()
    return message.splitlines()[0] if message else type(exc).__name__
