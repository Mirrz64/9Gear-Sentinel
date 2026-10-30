"""Run configured checks against their sources and collect the results."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from sentinel.checks.base import EvalContext
from sentinel.checks.registry import get_impl
from sentinel.config.models import SentinelConfig, TableSpec
from sentinel.connectors import ConnectorError, create_source_engine, short_error, table_target

Outcome = Literal["pass", "fail", "error", "skipped"]
PreviousLookup = Callable[[str], float | None]

EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_SETUP_PROBLEM = 2

# Fields that define *what* a check measures. Thresholds are left out on purpose,
# so tightening a limit keeps the check's history and baseline.
_IDENTITY_FIELDS = ("type", "column", "columns", "where", "name", "sql")


def status_for(outcome: str, severity: str) -> str:
    """What a person sees: PASS, FAIL, WARN, ERROR or SKIP."""
    if outcome == "fail":
        return "WARN" if severity == "warn" else "FAIL"
    return {"pass": "PASS", "error": "ERROR", "skipped": "SKIP"}.get(outcome, outcome.upper())


def check_key(source: str, table: str, check: Any) -> str:
    """Stable id for a check across runs, used to find its previous results."""
    identity = {name: getattr(check, name, None) for name in _IDENTITY_FIELDS}
    identity = {name: value for name, value in identity.items() if value is not None}
    payload = json.dumps({"source": source, "table": table, **identity}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class CheckResult:
    source: str
    table: str
    check_type: str
    check_key: str
    label: str
    severity: str
    outcome: Outcome
    observed: float | None
    message: str
    duration_ms: int

    @property
    def status(self) -> str:
        return status_for(self.outcome, self.severity)


@dataclass
class RunReport:
    started_at: datetime
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
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

    @property
    def status(self) -> str:
        if self.count("ERROR"):
            return "errored"
        if self.count("FAIL"):
            return "failed"
        if self.count("WARN"):
            return "warned"
        return "passed"

    def summary(self) -> str:
        total = len(self.results)
        parts = [f"{total} check{'s' if total != 1 else ''}"]
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
    previous: PreviousLookup | None = None,
) -> RunReport:
    """Run every selected check.

    ``previous`` looks up a check's last stored observed value by check key; the
    results store provides it. Without it, history-based checks act as a first run.
    """
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
                    report.results.append(_run_one(table, check, engine, now, previous))
    finally:
        for engine in engines.values():
            if isinstance(engine, Engine):
                engine.dispose()

    report.finished_at = datetime.now(UTC)
    return report


def _run_one(
    table: TableSpec,
    check: Any,
    engine: Engine | ConnectorError,
    now: datetime,
    previous: PreviousLookup | None,
) -> CheckResult:
    key = check_key(table.source, table.table, check)

    def result(outcome: Outcome, observed: float | None, message: str, ms: int) -> CheckResult:
        return CheckResult(
            source=table.source,
            table=table.table,
            check_type=check.type,
            check_key=key,
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

    ctx = EvalContext(now=now, previous=_lookup(previous, key) if impl.uses_previous else None)
    started = time.perf_counter()
    try:
        with engine.connect() as conn:
            row = conn.execute(impl.build(check, table_target(table.table))).one()
        evaluation = impl.evaluate(check, row, ctx)
    except SQLAlchemyError as exc:
        return result("error", None, short_error(exc), _elapsed_ms(started))
    except (TypeError, ValueError) as exc:
        return result("error", None, str(exc), _elapsed_ms(started))

    outcome: Outcome = "pass" if evaluation.passed else "fail"
    return result(outcome, evaluation.observed, evaluation.message, _elapsed_ms(started))


def _lookup(previous: PreviousLookup | None, key: str) -> float | None:
    if previous is None:
        return None
    try:
        return previous(key)
    except SQLAlchemyError:
        return None


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
