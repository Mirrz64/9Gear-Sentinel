"""Find rows whose reference has no match in another table (orphans).

The checked column is qualified with its table name inside the query. Without
that, a parent table with a column of the same name (customers.customer_id) would
shadow it and every row would look matched.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, column, func, literal_column, select, table
from sqlalchemy.sql.expression import Executable, TableClause

from sentinel.checks.base import (
    SAMPLE_SIZE,
    CheckImpl,
    EvalContext,
    Evaluation,
    apply_where,
    plural,
    show_value,
)
from sentinel.config.models import ForeignKeyCheck


def _child(spec: ForeignKeyCheck, target: TableClause) -> TableClause:
    """The checked table, with the checked column attached so it can be qualified."""
    return table(target.name, column(spec.column), schema=target.schema)


def _orphan_conditions(spec: ForeignKeyCheck, child: TableClause) -> list[ColumnElement[bool]]:
    """Non-null references with no matching row in the parent table."""
    schema, _, name = spec.ref_table.rpartition(".")
    parent = table(name, column(spec.ref_column), schema=schema or None).alias("ref")
    match = (
        select(literal_column("1"))
        .select_from(parent)
        .where(parent.c[spec.ref_column] == child.c[spec.column])
        .correlate(child)
        .exists()
    )
    return [child.c[spec.column].is_not(None), ~match]


def build(spec: ForeignKeyCheck, target: TableClause) -> Executable:
    child = _child(spec, target)
    query = select(func.count()).select_from(child).where(*_orphan_conditions(spec, child))
    return apply_where(query, spec)


def _reference(spec: ForeignKeyCheck) -> str:
    return f"{spec.ref_table}({spec.ref_column})"


def evaluate(spec: ForeignKeyCheck, row: Any, ctx: EvalContext) -> Evaluation:
    orphans = int(row[0] or 0)
    if orphans:
        return Evaluation(
            False,
            orphans,
            f"{plural(orphans, 'row')} with a {spec.column} not found in {_reference(spec)}",
        )
    return Evaluation(True, 0, f"every {spec.column} exists in {_reference(spec)}")


def sample(spec: ForeignKeyCheck, target: TableClause) -> Executable:
    """The most common orphaned values first."""
    child = _child(spec, target)
    col = child.c[spec.column]
    query = (
        select(col)
        .select_from(child)
        .where(*_orphan_conditions(spec, child))
        .group_by(col)
        .order_by(func.count().desc(), col)
        .limit(SAMPLE_SIZE)
    )
    return apply_where(query, spec)


def describe_sample(spec: ForeignKeyCheck, rows: Sequence[Any]) -> str:
    return "e.g. " + ", ".join(show_value(row[0]) for row in rows)


IMPL = CheckImpl(build=build, evaluate=evaluate, sample=sample, describe_sample=describe_sample)
