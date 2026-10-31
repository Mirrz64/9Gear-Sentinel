"""Shared types and helpers for check implementations."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import ColumnElement, Select, text
from sqlalchemy.sql.expression import Executable, TableClause

# Any Select, whatever its column types (works with SQLAlchemy 2.0 and 2.1 typing).
SelectT = TypeVar("SelectT", bound=Select)


@dataclass(frozen=True)
class Evaluation:
    passed: bool
    observed: float | None
    message: str


@dataclass(frozen=True)
class EvalContext:
    """What a check may need beyond its own query result."""

    now: datetime
    previous: float | None = None  # last stored observed value for this check, if any


@dataclass(frozen=True)
class CheckImpl:
    """How to query and judge one check type.

    build() returns a query whose single row holds everything evaluate() needs,
    so evaluate() can be unit-tested without a database.
    """

    build: Callable[[Any, TableClause], Executable]
    evaluate: Callable[[Any, Any, EvalContext], Evaluation]
    uses_previous: bool = False
    # Optional: when the check fails, fetch a few offending values to show the user.
    sample: Callable[[Any, TableClause], Executable] | None = None
    describe_sample: Callable[[Any, Sequence[Any]], str] | None = None


def apply_where(query: SelectT, spec: Any) -> SelectT:
    where = getattr(spec, "where", None)
    return query.where(text(where)) if where else query


def not_null_all(columns: Sequence[ColumnElement[Any]]) -> list[ColumnElement[bool]]:
    return [col.is_not(None) for col in columns]


SAMPLE_SIZE = 5
_MAX_VALUE_LENGTH = 40


def show_value(value: object) -> str:
    """How an example value appears in a message: strings quoted, long values cut."""
    text = f"'{value}'" if isinstance(value, str) else str(value)
    if len(text) > _MAX_VALUE_LENGTH:
        text = text[: _MAX_VALUE_LENGTH - 1] + "…"
    return text


def plural(count: int, word: str) -> str:
    return f"{count:,} {word}" if count == 1 else f"{count:,} {word}s"


def fmt_number(value: float) -> str:
    """2.49 -> '2.49', 1.0 -> '1', 12.5 -> '12.5'."""
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"
