"""Map check type names to their implementations."""

from __future__ import annotations

from sentinel.checks import freshness, nulls, row_count, unique
from sentinel.checks.base import CheckImpl

REGISTRY: dict[str, CheckImpl] = {
    "freshness": freshness.IMPL,
    "row_count": row_count.IMPL,
    "not_null": nulls.NOT_NULL,
    "null_rate": nulls.NULL_RATE,
    "unique": unique.IMPL,
}


def get_impl(check_type: str) -> CheckImpl | None:
    return REGISTRY.get(check_type)
