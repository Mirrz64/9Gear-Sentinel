"""Shared types for check implementations."""

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
class CheckImpl:
    """How to query and judge one check type.

    build() returns a query whose first row holds everything evaluate() needs,
    so evaluate() can be unit-tested without a database.
    """

    build: Callable[[Any, TableClause], Executable]
    evaluate: Callable[[Any, Any, datetime], Evaluation]


def apply_where(query: SelectT, spec: Any) -> SelectT:
    where = getattr(spec, "where", None)
    return query.where(text(where)) if where else query


def not_null_all(columns: Sequence[ColumnElement[Any]]) -> list[ColumnElement[bool]]:
    return [col.is_not(None) for col in columns]


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"
