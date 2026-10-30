from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.sql.expression import Executable, TableClause

from sentinel.checks.base import CheckImpl, EvalContext, Evaluation, apply_where, fmt_number, plural
from sentinel.config.models import RowCountChangeCheck, RowCountCheck


def build_count(spec: Any, target: TableClause) -> Executable:
    return apply_where(select(func.count()).select_from(target), spec)


def evaluate(spec: RowCountCheck, row: Any, ctx: EvalContext) -> Evaluation:
    count = int(row[0] or 0)
    if spec.min is not None and count < spec.min:
        return Evaluation(False, count, f"{plural(count, 'row')}, expected at least {spec.min:,}")
    if spec.max is not None and count > spec.max:
        return Evaluation(False, count, f"{plural(count, 'row')}, expected at most {spec.max:,}")
    return Evaluation(True, count, plural(count, "row"))


def evaluate_change(spec: RowCountChangeCheck, row: Any, ctx: EvalContext) -> Evaluation:
    """Compare against the last stored count. Observed is the count, so it becomes
    the next run's baseline."""
    count = int(row[0] or 0)
    if ctx.previous is None:
        return Evaluation(True, count, f"first run; baseline set at {plural(count, 'row')}")

    previous = int(ctx.previous)
    if previous == 0:
        return Evaluation(True, count, f"{plural(count, 'row')} (previous run had 0)")

    change = (count - previous) / previous * 100
    detail = f"from {previous:,} to {count:,} rows"
    if spec.max_drop_pct is not None and -change > spec.max_drop_pct:
        return Evaluation(
            False,
            count,
            f"dropped {fmt_number(-change)}% {detail}, limit {fmt_number(spec.max_drop_pct)}%",
        )
    if spec.max_growth_pct is not None and change > spec.max_growth_pct:
        return Evaluation(
            False,
            count,
            f"grew {fmt_number(change)}% {detail}, limit {fmt_number(spec.max_growth_pct)}%",
        )
    direction = "up" if change > 0 else "down" if change < 0 else "unchanged"
    if direction == "unchanged":
        return Evaluation(True, count, f"unchanged at {plural(count, 'row')}")
    return Evaluation(True, count, f"{direction} {fmt_number(abs(change))}% {detail}")


IMPL = CheckImpl(build=build_count, evaluate=evaluate)
CHANGE = CheckImpl(build=build_count, evaluate=evaluate_change, uses_previous=True)
