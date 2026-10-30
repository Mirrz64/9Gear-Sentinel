"""Run configured checks against their sources and collect the results."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from sentinel.checks.registry import get_impl
from sentinel.config.models import SentinelConfig, TableSpec
from sentinel.connectors import ConnectorError, create_source_engine, short_error, table_target

Outcome = Literal["pass", "fail", "error", "skipped"]

EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_SETUP_PROBLEM = 2


@dataclass(frozen=True)
class CheckResult:
    source: str
    table: str
    check_type: str
    label: str
    severity: str
    outcome: Outcome
    observed: float | None
    message: str
    duration_ms: int

    @property
    def status(self) -> str:
        """What a person sees: PASS, FAIL, WARN, ERROR or SKIP."""
        if self.outcome == "fail":
            return "WARN" if self.severity == "warn" else "FAIL"
        return {"pass": "PASS", "error": "ERROR", "skipped": "SKIP"}[self.outcome]


@dataclass
class RunReport:
    started_at: datetime
    finished_at: datetime | None = None
    results: list[CheckResult] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for result in self.results if result.status == status)

    @property
    def exit_code(self) -> int:
        """2 if any check couldn't run, 1 if an error-severity check failed, else 0."""
        if any(result.outcome == "error" for result in self.results):
            return EXIT_SETUP_PROBLEM
        if any(result.status == "FAIL" for result in self.results):
            return EXIT_CHECK_FAILED
        return EXIT_OK

    def summary(self) -> str:
        parts = [f"{len(self.results)} checks"]
        for status, word in (
            ("PASS", "passed"),
            ("FAIL", "failed"),
            ("WARN", "warned"),
            ("ERROR", "errored"),
            ("SKIP", "skipped"),
        ):
            if count := self.count(status):
                parts.append(f"{count} {word}")
        return ", ".join(parts)


@dataclass(frozen=True)
class Selection:
    """Optional filters from the command line. Empty means 'everything'."""

    sources: Sequence[str] = ()
    tables: Sequence[str] = ()
    check_types: Sequence[str] = ()
    tags: Sequence[str] = ()

    def wants_table(self, table: TableSpec) -> bool:
        if self.sources and table.source not in self.sources:
            return False
        return not self.tables or table.table in self.tables

    def wants_check(self, table: TableSpec, check: Any) -> bool:
        if self.check_types and check.type not in self.check_types:
            return False
        if self.tags:
            return bool(set(self.tags) & (set(table.tags) | set(check.tags)))
        return True


def describe(check: Any) -> str:
    """A short label for a check, e.g. 'unique(order_id)'."""
    if check.name:
        return str(check.name)
    column = getattr(check, "column", None)
    columns = getattr(check, "columns", None)
    if column:
        return f"{check.type}({column})"
    if columns:
        return f"{check.type}({', '.join(columns)})"
    return str(check.type)


def run_checks(
    config: SentinelConfig,
    selection: Selection | None = None,
    now: datetime | None = None,
) -> RunReport:
    selection = selection or Selection()
    now = now or datetime.now(UTC)
    report = RunReport(started_at=datetime.now(UTC))
    engines: dict[str, Engine | ConnectorError] = {}

    try:
        for table in config.tables:
            if not selection.wants_table(table):
                continue
            engine = engines.get(table.source)
            if engine is None:
                try:
                    engine = create_source_engine(table.source, config.sources[table.source])
                except ConnectorError as exc:
                    engine = exc
                engines[table.source] = engine

            for check in table.checks:
                if selection.wants_check(table, check):
                    report.results.append(_run_one(table, check, engine, now))
    finally:
        for engine in engines.values():
            if isinstance(engine, Engine):
                engine.dispose()

    report.finished_at = datetime.now(UTC)
    return report


def _run_one(
    table: TableSpec, check: Any, engine: Engine | ConnectorError, now: datetime
) -> CheckResult:
    def result(outcome: Outcome, observed: float | None, message: str, ms: int) -> CheckResult:
        return CheckResult(
            source=table.source,
            table=table.table,
            check_type=check.type,
            label=describe(check),
            severity=check.severity,
            outcome=outcome,
            observed=observed,
            message=message,
            duration_ms=ms,
        )

    if isinstance(engine, ConnectorError):
        return result("error", None, str(engine), 0)

    impl = get_impl(check.type)
    if impl is None:
        return result("skipped", None, "not implemented yet", 0)

    started = time.perf_counter()
    try:
        with engine.connect() as conn:
            row = conn.execute(impl.build(check, table_target(table.table))).one()
        evaluation = impl.evaluate(check, row, now)
    except SQLAlchemyError as exc:
        return result("error", None, short_error(exc), _elapsed_ms(started))
    except (TypeError, ValueError) as exc:
        return result("error", None, str(exc), _elapsed_ms(started))

    outcome: Outcome = "pass" if evaluation.passed else "fail"
    return result(outcome, evaluation.observed, evaluation.message, _elapsed_ms(started))


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
