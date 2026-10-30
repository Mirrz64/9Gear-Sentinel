"""Detect added, removed and retyped columns against a stored schema snapshot.

Unlike other checks this one inspects table metadata instead of running a query,
so the runner calls it directly. A drift keeps failing until someone accepts the
new schema with `sentinel snapshot-schema`.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from sqlalchemy import Connection, inspect

from sentinel.checks.base import Evaluation, plural
from sentinel.config.models import SchemaDriftCheck

Columns = tuple[tuple[str, str], ...]

_SHOW_CHANGES = 5


def read_columns(conn: Connection, table_name: str) -> Columns:
    schema, _, name = table_name.rpartition(".")
    columns = inspect(conn).get_columns(name, schema=schema or None)
    return tuple((str(col["name"]), _type_name(col["type"], conn)) for col in columns)


def _type_name(column_type: Any, conn: Connection) -> str:
    try:
        return str(column_type.compile(dialect=conn.dialect))
    except Exception:  # some dialect types can't compile on their own
        return type(column_type).__name__


def diff(baseline: Columns, current: Columns, ignore: Collection[str] = ()) -> list[str]:
    old = {name: kind for name, kind in baseline if name not in ignore}
    new = {name: kind for name, kind in current if name not in ignore}
    changes = [f"added {name} ({new[name]})" for name in new if name not in old]
    changes += [f"removed {name}" for name in old if name not in new]
    changes += [
        f"{name} changed {old[name]} -> {new[name]}"
        for name in old
        if name in new and old[name] != new[name]
    ]
    return changes


def evaluate(spec: SchemaDriftCheck, current: Columns, baseline: Columns | None) -> Evaluation:
    if baseline is None:
        return Evaluation(True, 0, f"no baseline yet; recorded {plural(len(current), 'column')}")

    changes = diff(baseline, current, spec.ignore_columns)
    if not changes:
        return Evaluation(True, 0, f"schema unchanged ({plural(len(current), 'column')})")

    shown = "; ".join(changes[:_SHOW_CHANGES])
    extra = len(changes) - _SHOW_CHANGES
    more = f"; +{extra} more" if extra > 0 else ""
    return Evaluation(False, len(changes), f"{plural(len(changes), 'change')}: {shown}{more}")
