from datetime import UTC, datetime, timedelta

import pytest

from sentinel.checks import accepted_values, custom_sql, freshness, nulls, row_count, unique
from sentinel.checks.base import EvalContext, fmt_number
from sentinel.config.models import (
    AcceptedValuesCheck,
    CustomSqlCheck,
    FreshnessCheck,
    NotNullCheck,
    NullRateCheck,
    RowCountChangeCheck,
    RowCountCheck,
    UniqueCheck,
)

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
CTX = EvalContext(now=NOW)


def fresh(max_age: str = "6h") -> FreshnessCheck:
    return FreshnessCheck(type="freshness", column="updated_at", max_age=max_age)


class TestFreshness:
    def test_recent_value_passes(self) -> None:
        result = freshness.evaluate(fresh(), (NOW - timedelta(hours=2),), CTX)
        assert result.passed
        assert result.observed == 7200
        assert "2h old" in result.message

    def test_old_value_fails(self) -> None:
        result = freshness.evaluate(fresh(), (NOW - timedelta(days=1),), CTX)
        assert not result.passed
        assert "1d old (limit 6h)" in result.message

    def test_age_is_rounded_to_two_units(self) -> None:
        age = timedelta(days=3, minutes=1, seconds=4)
        result = freshness.evaluate(fresh(), (NOW - age,), CTX)
        assert "3d 1m old" in result.message

    def test_exactly_on_the_limit_passes(self) -> None:
        assert freshness.evaluate(fresh(), (NOW - timedelta(hours=6),), CTX).passed

    def test_empty_table_fails(self) -> None:
        result = freshness.evaluate(fresh(), (None,), CTX)
        assert not result.passed
        assert "empty" in result.message

    def test_naive_and_string_timestamps_are_treated_as_utc(self) -> None:
        naive = (NOW - timedelta(hours=1)).replace(tzinfo=None)
        assert freshness.evaluate(fresh(), (naive,), CTX).observed == 3600
        assert freshness.evaluate(fresh(), ("2026-11-02 11:00:00",), CTX).observed == 3600

    def test_future_timestamp_passes(self) -> None:
        assert freshness.evaluate(fresh(), (NOW + timedelta(hours=1),), CTX).passed

    def test_non_timestamp_column_raises(self) -> None:
        with pytest.raises(TypeError):
            freshness.evaluate(fresh(), (42,), CTX)


class TestRowCount:
    def test_within_bounds(self) -> None:
        spec = RowCountCheck(type="row_count", min=1, max=10)
        assert row_count.evaluate(spec, (5,), CTX).passed

    def test_below_min(self) -> None:
        spec = RowCountCheck(type="row_count", min=1)
        result = row_count.evaluate(spec, (0,), CTX)
        assert not result.passed
        assert "expected at least 1" in result.message

    def test_above_max(self) -> None:
        spec = RowCountCheck(type="row_count", max=10)
        assert not row_count.evaluate(spec, (11,), CTX).passed

    def test_large_counts_have_separators(self) -> None:
        spec = RowCountCheck(type="row_count", min=1)
        assert row_count.evaluate(spec, (1003,), CTX).message == "1,003 rows"


class TestRowCountChange:
    spec = RowCountChangeCheck(type="row_count_change", max_drop_pct=30, max_growth_pct=50)

    def ctx(self, previous: float | None) -> EvalContext:
        return EvalContext(now=NOW, previous=previous)

    def test_first_run_sets_baseline(self) -> None:
        result = row_count.evaluate_change(self.spec, (1000,), self.ctx(None))
        assert result.passed
        assert result.observed == 1000
        assert "baseline" in result.message

    def test_small_change_passes(self) -> None:
        result = row_count.evaluate_change(self.spec, (900,), self.ctx(1000))
        assert result.passed
        assert "down 10% from 1,000 to 900 rows" in result.message

    def test_big_drop_fails(self) -> None:
        result = row_count.evaluate_change(self.spec, (600,), self.ctx(1000))
        assert not result.passed
        assert "dropped 40%" in result.message
        assert result.observed == 600

    def test_big_growth_fails(self) -> None:
        result = row_count.evaluate_change(self.spec, (1600,), self.ctx(1000))
        assert not result.passed
        assert "grew 60%" in result.message

    def test_unchanged(self) -> None:
        assert "unchanged" in row_count.evaluate_change(self.spec, (5,), self.ctx(5)).message

    def test_previous_zero_passes(self) -> None:
        assert row_count.evaluate_change(self.spec, (10,), self.ctx(0)).passed

    def test_only_drop_limit_set_allows_growth(self) -> None:
        spec = RowCountChangeCheck(type="row_count_change", max_drop_pct=10)
        assert row_count.evaluate_change(spec, (5000,), self.ctx(1000)).passed


class TestNulls:
    def test_not_null(self) -> None:
        spec = NotNullCheck(type="not_null", column="email")
        assert nulls.evaluate_not_null(spec, (0,), CTX).passed
        assert not nulls.evaluate_not_null(spec, (3,), CTX).passed

    def test_null_rate_under_and_over_limit(self) -> None:
        spec = NullRateCheck(type="null_rate", column="x", max_pct=5)
        assert nulls.evaluate_null_rate(spec, (100, 5), CTX).passed
        result = nulls.evaluate_null_rate(spec, (100, 6), CTX)
        assert not result.passed
        assert result.observed == 6.0

    def test_null_rate_message_has_clean_numbers(self) -> None:
        spec = NullRateCheck(type="null_rate", column="x", max_pct=1)
        result = nulls.evaluate_null_rate(spec, (1003, 25), CTX)
        assert result.message == "2.49% null in x (25 of 1,003), limit 1%"

    def test_null_rate_empty_table_passes(self) -> None:
        spec = NullRateCheck(type="null_rate", column="x")
        assert nulls.evaluate_null_rate(spec, (0, None), CTX).passed


class TestUnique:
    def test_duplicates_fail(self) -> None:
        spec = UniqueCheck(type="unique", columns=["a", "b"])
        result = unique.evaluate(spec, (2,), CTX)
        assert not result.passed
        assert "2 duplicate keys in (a, b)" in result.message

    def test_no_duplicates_pass(self) -> None:
        spec = UniqueCheck(type="unique", columns=["a"])
        assert unique.evaluate(spec, (0,), CTX).passed


class TestAcceptedValues:
    def test_all_accepted(self) -> None:
        spec = AcceptedValuesCheck(type="accepted_values", column="s", values=["a", "b"])
        assert accepted_values.evaluate(spec, (0,), CTX).passed

    def test_outside_values_fail(self) -> None:
        spec = AcceptedValuesCheck(type="accepted_values", column="s", values=["a", "b"])
        result = accepted_values.evaluate(spec, (4,), CTX)
        assert not result.passed
        assert "4 rows with s outside [a, b]" in result.message

    def test_long_value_lists_are_shortened(self) -> None:
        values = [str(n) for n in range(8)]
        spec = AcceptedValuesCheck(type="accepted_values", column="s", values=values)
        assert "+3 more" in accepted_values.evaluate(spec, (1,), CTX).message


class TestCustomSql:
    spec = CustomSqlCheck(type="custom_sql", name="no_orphans", sql="select 1")

    def test_no_rows_passes(self) -> None:
        assert custom_sql.evaluate(self.spec, (0,), CTX).passed

    def test_rows_fail(self) -> None:
        result = custom_sql.evaluate(self.spec, (3,), CTX)
        assert not result.passed
        assert "3 rows returned" in result.message


@pytest.mark.parametrize(
    ("value", "expected"), [(1.0, "1"), (2.49, "2.49"), (12.5, "12.5"), (0.0, "0"), (100, "100")]
)
def test_fmt_number(value: float, expected: str) -> None:
    assert fmt_number(value) == expected
