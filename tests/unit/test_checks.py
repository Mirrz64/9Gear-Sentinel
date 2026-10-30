from datetime import UTC, datetime, timedelta

import pytest

from sentinel.checks import freshness, nulls, row_count, unique
from sentinel.config.models import (
    FreshnessCheck,
    NotNullCheck,
    NullRateCheck,
    RowCountCheck,
    UniqueCheck,
)

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def fresh(max_age: str = "6h") -> FreshnessCheck:
    return FreshnessCheck(type="freshness", column="updated_at", max_age=max_age)


class TestFreshness:
    def test_recent_value_passes(self) -> None:
        result = freshness.evaluate(fresh(), (NOW - timedelta(hours=2),), NOW)
        assert result.passed
        assert result.observed == 7200
        assert "2h old" in result.message

    def test_old_value_fails(self) -> None:
        result = freshness.evaluate(fresh(), (NOW - timedelta(days=1),), NOW)
        assert not result.passed
        assert "1d old (limit 6h)" in result.message

    def test_exactly_on_the_limit_passes(self) -> None:
        assert freshness.evaluate(fresh(), (NOW - timedelta(hours=6),), NOW).passed

    def test_empty_table_fails(self) -> None:
        result = freshness.evaluate(fresh(), (None,), NOW)
        assert not result.passed
        assert "empty" in result.message

    def test_naive_and_string_timestamps_are_treated_as_utc(self) -> None:
        naive = (NOW - timedelta(hours=1)).replace(tzinfo=None)
        assert freshness.evaluate(fresh(), (naive,), NOW).observed == 3600
        assert freshness.evaluate(fresh(), ("2026-11-02 11:00:00",), NOW).observed == 3600

    def test_future_timestamp_passes(self) -> None:
        assert freshness.evaluate(fresh(), (NOW + timedelta(hours=1),), NOW).passed

    def test_non_timestamp_column_raises(self) -> None:
        with pytest.raises(TypeError):
            freshness.evaluate(fresh(), (42,), NOW)


class TestRowCount:
    def test_within_bounds(self) -> None:
        spec = RowCountCheck(type="row_count", min=1, max=10)
        assert row_count.evaluate(spec, (5,), NOW).passed

    def test_below_min(self) -> None:
        spec = RowCountCheck(type="row_count", min=1)
        result = row_count.evaluate(spec, (0,), NOW)
        assert not result.passed
        assert "expected at least 1" in result.message

    def test_above_max(self) -> None:
        spec = RowCountCheck(type="row_count", max=10)
        assert not row_count.evaluate(spec, (11,), NOW).passed


class TestNulls:
    def test_not_null(self) -> None:
        spec = NotNullCheck(type="not_null", column="email")
        assert nulls.evaluate_not_null(spec, (0,), NOW).passed
        assert not nulls.evaluate_not_null(spec, (3,), NOW).passed

    def test_null_rate_under_and_over_limit(self) -> None:
        spec = NullRateCheck(type="null_rate", column="x", max_pct=5)
        assert nulls.evaluate_null_rate(spec, (100, 5), NOW).passed
        result = nulls.evaluate_null_rate(spec, (100, 6), NOW)
        assert not result.passed
        assert result.observed == 6.0

    def test_null_rate_empty_table_passes(self) -> None:
        spec = NullRateCheck(type="null_rate", column="x")
        assert nulls.evaluate_null_rate(spec, (0, None), NOW).passed


class TestUnique:
    def test_duplicates_fail(self) -> None:
        spec = UniqueCheck(type="unique", columns=["a", "b"])
        result = unique.evaluate(spec, (2,), NOW)
        assert not result.passed
        assert "2 duplicate keys in (a, b)" in result.message

    def test_no_duplicates_pass(self) -> None:
        spec = UniqueCheck(type="unique", columns=["a"])
        assert unique.evaluate(spec, (0,), NOW).passed
