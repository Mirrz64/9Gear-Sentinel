"""Results store schema. Table names are prefixed so a shared Postgres store won't clash."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, MetaData, String, Table, Text

metadata = MetaData()

runs = Table(
    "sentinel_runs",
    metadata,
    Column("run_id", String(32), primary_key=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("status", String(16), nullable=False),
    Column("triggered_by", String(16), nullable=False),
    Column("sentinel_version", String(32), nullable=False),
)

check_results = Table(
    "sentinel_check_results",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(32), ForeignKey("sentinel_runs.run_id"), nullable=False, index=True),
    Column("checked_at", DateTime(timezone=True), nullable=False, index=True),
    Column("check_key", String(32), nullable=False, index=True),
    Column("source", String(200), nullable=False),
    Column("table_name", String(400), nullable=False),
    Column("check_type", String(40), nullable=False),
    Column("label", String(400), nullable=False),
    Column("severity", String(8), nullable=False),
    Column("outcome", String(8), nullable=False),
    Column("observed", Float),
    Column("message", Text, nullable=False),
    Column("duration_ms", Integer, nullable=False),
)

# Used by schema_drift (week 4); created now so the store schema is stable.
schema_snapshots = Table(
    "sentinel_schema_snapshots",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source", String(200), nullable=False),
    Column("table_name", String(400), nullable=False, index=True),
    Column("columns", Text, nullable=False),
    Column("captured_at", DateTime(timezone=True), nullable=False),
)
