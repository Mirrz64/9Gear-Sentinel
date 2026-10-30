"""Save runs and read back history from the results store."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, create_engine, make_url, select
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

from sentinel import __version__
from sentinel.checks.schema_drift import Columns
from sentinel.connectors import short_error
from sentinel.runner import RunReport, status_for
from sentinel.store.tables import check_results, metadata, runs, schema_snapshots


class StoreError(Exception):
    """The results store couldn't be opened."""


@dataclass(frozen=True)
class HistoryRow:
    checked_at: datetime
    table_name: str
    check_type: str
    label: str
    severity: str
    outcome: str
    observed: float | None
    message: str

    @property
    def status(self) -> str:
        return status_for(self.outcome, self.severity)


@dataclass(frozen=True)
class StoredRun:
    run_id: str
    started_at: datetime
    status: str
    triggered_by: str
    results: list[HistoryRow]
    # check label -> statuses of its recent runs, oldest first (includes this run)
    trends: dict[str, list[str]]


class ResultStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def open(cls, url: str) -> ResultStore:
        """Open (and create if needed) the store. Relative SQLite paths are relative
        to the current directory."""
        try:
            parsed = make_url(url)
        except ArgumentError as exc:
            raise StoreError(f"invalid store URL ({exc})") from None

        if parsed.drivername == "postgresql":
            parsed = parsed.set(drivername="postgresql+psycopg")
        database = parsed.database
        if parsed.get_backend_name() == "sqlite" and database and database != ":memory:":
            Path(database).parent.mkdir(parents=True, exist_ok=True)

        try:
            engine = create_engine(parsed)
            metadata.create_all(engine)
        except (SQLAlchemyError, ModuleNotFoundError) as exc:
            raise StoreError(f"could not open the results store: {short_error(exc)}") from None
        return cls(engine)

    def close(self) -> None:
        self.engine.dispose()

    def save(self, report: RunReport, triggered_by: str = "cli") -> None:
        with self.engine.begin() as conn:
            conn.execute(
                runs.insert().values(
                    run_id=report.run_id,
                    started_at=report.started_at,
                    finished_at=report.finished_at,
                    status=report.status,
                    triggered_by=triggered_by,
                    sentinel_version=__version__,
                )
            )
            if report.results:
                conn.execute(
                    check_results.insert(),
                    [
                        {
                            "run_id": report.run_id,
                            "checked_at": report.started_at,
                            "check_key": result.check_key,
                            "source": result.source,
                            "table_name": result.table,
                            "check_type": result.check_type,
                            "label": result.label,
                            "severity": result.severity,
                            "outcome": result.outcome,
                            "observed": result.observed,
                            "message": result.message,
                            "duration_ms": result.duration_ms,
                        }
                        for result in report.results
                    ],
                )
            seen: set[tuple[str, str]] = set()
            for snapshot in report.new_snapshots:
                if (snapshot.source, snapshot.table) in seen:
                    continue
                seen.add((snapshot.source, snapshot.table))
                conn.execute(
                    schema_snapshots.insert().values(
                        source=snapshot.source,
                        table_name=snapshot.table,
                        columns=json.dumps([list(col) for col in snapshot.columns]),
                        captured_at=report.started_at,
                    )
                )

    def save_snapshot(self, source: str, table: str, columns: Columns) -> None:
        """Store a table's current columns as the new schema_drift baseline."""
        with self.engine.begin() as conn:
            conn.execute(
                schema_snapshots.insert().values(
                    source=source,
                    table_name=table,
                    columns=json.dumps([list(col) for col in columns]),
                    captured_at=datetime.now(UTC),
                )
            )

    def latest_snapshot(self, source: str, table: str) -> Columns | None:
        c = schema_snapshots.c
        query = (
            select(c["columns"])
            .where(c.source == source, c.table_name == table)
            .order_by(c.captured_at.desc(), c.id.desc())
            .limit(1)
        )
        with self.engine.connect() as conn:
            raw = conn.execute(query).scalar()
        if raw is None:
            return None
        return tuple((str(name), str(kind)) for name, kind in json.loads(raw))

    def last_status(self, key: str) -> str | None:
        """Status (PASS, FAIL, WARN, ERROR) of a check's most recent stored run."""
        c = check_results.c
        query = (
            select(c.outcome, c.severity)
            .where(c.check_key == key, c.outcome != "skipped")
            .order_by(c.checked_at.desc(), c.id.desc())
            .limit(1)
        )
        with self.engine.connect() as conn:
            row = conn.execute(query).first()
        return status_for(row.outcome, row.severity) if row is not None else None

    def last_observed(self, key: str) -> float | None:
        """The most recent measured value for a check that ran (passed or failed)."""
        query = (
            select(check_results.c.observed)
            .where(
                check_results.c.check_key == key,
                check_results.c.observed.is_not(None),
                check_results.c.outcome.in_(["pass", "fail"]),
            )
            .order_by(check_results.c.checked_at.desc(), check_results.c.id.desc())
            .limit(1)
        )
        with self.engine.connect() as conn:
            value = conn.execute(query).scalar()
        return float(value) if value is not None else None

    def history(
        self,
        table: str | None = None,
        check_type: str | None = None,
        limit: int = 20,
    ) -> list[HistoryRow]:
        c = check_results.c
        query = select(
            c.checked_at,
            c.table_name,
            c.check_type,
            c.label,
            c.severity,
            c.outcome,
            c.observed,
            c.message,
        )
        if table:
            query = query.where(c.table_name == table)
        if check_type:
            query = query.where(c.check_type == check_type)
        query = query.order_by(c.checked_at.desc(), c.id.desc()).limit(limit)

        with self.engine.connect() as conn:
            rows = conn.execute(query).all()
        return [
            HistoryRow(
                checked_at=row.checked_at,
                table_name=row.table_name,
                check_type=row.check_type,
                label=row.label,
                severity=row.severity,
                outcome=row.outcome,
                observed=row.observed,
                message=row.message,
            )
            for row in rows
        ]

    def latest_run(self, trend_length: int = 10) -> StoredRun | None:
        """The newest stored run with its results and each check's recent trend."""
        r, c = runs.c, check_results.c
        with self.engine.connect() as conn:
            run = conn.execute(
                select(r.run_id, r.started_at, r.status, r.triggered_by)
                .order_by(r.started_at.desc())
                .limit(1)
            ).first()
            if run is None:
                return None
            rows = conn.execute(
                select(
                    c.checked_at,
                    c.table_name,
                    c.check_type,
                    c.label,
                    c.severity,
                    c.outcome,
                    c.observed,
                    c.message,
                    c.check_key,
                )
                .where(c.run_id == run.run_id)
                .order_by(c.id)
            ).all()

            results: list[HistoryRow] = []
            trends: dict[str, list[str]] = {}
            for row in rows:
                results.append(
                    HistoryRow(
                        checked_at=row.checked_at,
                        table_name=row.table_name,
                        check_type=row.check_type,
                        label=row.label,
                        severity=row.severity,
                        outcome=row.outcome,
                        observed=row.observed,
                        message=row.message,
                    )
                )
                recent = conn.execute(
                    select(c.outcome, c.severity)
                    .where(c.check_key == row.check_key, c.checked_at <= row.checked_at)
                    .order_by(c.checked_at.desc(), c.id.desc())
                    .limit(trend_length)
                ).all()
                trends[f"{row.table_name}:{row.label}"] = [
                    status_for(item.outcome, item.severity) for item in reversed(recent)
                ]

        return StoredRun(
            run_id=run.run_id,
            started_at=run.started_at,
            status=run.status,
            triggered_by=run.triggered_by,
            results=results,
            trends=trends,
        )
