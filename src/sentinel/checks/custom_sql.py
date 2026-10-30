from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.sql.expression import Executable, TableClause

from sentinel.checks.base import CheckImpl, EvalContext, Evaluation, plural
from sentinel.config.models import CustomSqlCheck


def build(spec: CustomSqlCheck, target: TableClause) -> Executable:
    """Wrap the user's query and count its rows. Any row returned is a failure.

    `where` is ignored here: put filters inside the SQL itself.
    """
    sql = spec.sql.strip().rstrip(";").strip()
    user_query = text(sql).columns().subquery("sentinel_custom")
    return select(func.count()).select_from(user_query)


def evaluate(spec: CustomSqlCheck, row: Any, ctx: EvalContext) -> Evaluation:
    rows = int(row[0] or 0)
    if rows:
        return Evaluation(False, rows, f"{plural(rows, 'row')} returned; expected none")
    return Evaluation(True, 0, "no rows returned")


IMPL = CheckImpl(build=build, evaluate=evaluate)
