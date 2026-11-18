"""column_range and foreign_key, run end to end against the SQLite demo database."""

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from sentinel.config import SentinelConfig
from sentinel.config.models import ColumnRangeCheck, ForeignKeyCheck
from sentinel.runner import preview_sql, run_checks
from tests.conftest import NOW

MakeConfig = Callable[[str], SentinelConfig]


def on_table(table: str, *lines: str) -> str:
    return f"  - source: local\n    table: {table}\n    checks:\n" + "".join(
        f"      - {line}\n" for line in lines
    )


class TestColumnRange:
    def test_values_above_the_maximum_fail_with_examples(self, make_config: MakeConfig) -> None:
        config = make_config(
            on_table("orders", "column_range: { column: order_id, min: 1, max: 90 }")
        )
        (result,) = run_checks(config, now=NOW).results
        assert result.status == "FAIL"
        assert result.observed == 10
        assert result.message == (
            "10 values out of range in order_id (expected between 1 and 90; min 1, max 100); "
            "e.g. 91, 92, 93, 94, 95"
        )

    def test_values_inside_the_range_pass(self, make_config: MakeConfig) -> None:
        config = make_config(
            on_table("orders", "column_range: { column: order_id, min: 1, max: 100 }")
        )
        (result,) = run_checks(config, now=NOW).results
        assert result.status == "PASS"
        assert result.message == "all values between 1 and 100 (min 1, max 100)"

    def test_a_single_bound_is_enough(self, make_config: MakeConfig) -> None:
        config = make_config(on_table("customers", "column_range: { column: id, min: 1 }"))
        (result,) = run_checks(config, now=NOW).results
        assert result.status == "PASS"
        assert result.message == "all values at least 1 (min 1, max 50)"

    def test_zero_is_a_real_bound(self, make_config: MakeConfig) -> None:
        config = make_config(on_table("customers", "column_range: { column: id, max: 0 }"))
        (result,) = run_checks(config, now=NOW).results
        assert result.status == "FAIL"
        assert "expected at most 0" in result.message

    def test_where_limits_which_rows_are_checked(self, make_config: MakeConfig) -> None:
        config = make_config(
            on_table(
                "orders",
                "column_range: { column: order_id, max: 90, where: 'order_id <= 50' }",
            )
        )
        (result,) = run_checks(config, now=NOW).results
        assert result.status == "PASS"

    def test_empty_table_passes(self, make_config: MakeConfig) -> None:
        config = make_config(on_table("empty_table", "column_range: { column: id, min: 0 }"))
        (result,) = run_checks(config, now=NOW).results
        assert result.status == "PASS"
        assert result.message == "no values in id to check"

    def test_text_column_is_reported_as_an_error(self, make_config: MakeConfig) -> None:
        config = make_config(on_table("customers", "column_range: { column: email, min: 0 }"))
        (result,) = run_checks(config, now=NOW).results
        assert result.status == "ERROR"
        assert "not a numeric column" in result.message

    def test_options_are_validated(self) -> None:
        with pytest.raises(ValidationError, match="at least one of min or max"):
            ColumnRangeCheck(type="column_range", column="amount")
        with pytest.raises(ValidationError, match="greater than max"):
            ColumnRangeCheck(type="column_range", column="amount", min=10, max=1)


class TestForeignKey:
    FK = "foreign_key: { column: customer_id, ref_table: customers, ref_column: id }"

    def test_orphaned_references_fail_with_examples(self, make_config: MakeConfig) -> None:
        config = make_config(on_table("orders", self.FK))
        (result,) = run_checks(config, now=NOW).results
        assert result.status == "FAIL"
        # customer_ids 51-100 have no customer, except the five that are null (not counted).
        assert result.observed == 45
        assert result.message == (
            "45 rows with a customer_id not found in customers(id); e.g. 51, 52, 53, 54, 55"
        )

    def test_where_limits_which_rows_are_checked(self, make_config: MakeConfig) -> None:
        config = make_config(
            on_table(
                "orders",
                "foreign_key: { column: customer_id, ref_table: customers, ref_column: id, "
                "where: 'order_id <= 50' }",
            )
        )
        (result,) = run_checks(config, now=NOW).results
        assert result.status == "PASS"
        assert result.message == "every customer_id exists in customers(id)"

    def test_a_table_can_reference_itself(self, make_config: MakeConfig) -> None:
        config = make_config(
            on_table(
                "orders",
                "foreign_key: { column: customer_id, ref_table: orders, ref_column: order_id }",
            )
        )
        (result,) = run_checks(config, now=NOW).results
        assert result.status == "PASS"

    def test_missing_parent_table_is_reported_as_an_error(self, make_config: MakeConfig) -> None:
        config = make_config(
            on_table(
                "orders",
                "foreign_key: { column: customer_id, ref_table: nope, ref_column: id }",
            )
        )
        (result,) = run_checks(config, now=NOW).results
        assert result.status == "ERROR"

    def test_the_checked_column_is_qualified_in_the_sql(self, make_config: MakeConfig) -> None:
        config = make_config(on_table("orders", self.FK))
        (preview,) = preview_sql(config)
        assert "orders.customer_id" in preview.sql
        assert "ref.id" in preview.sql

    def test_two_references_on_one_column_keep_separate_history(
        self, make_config: MakeConfig
    ) -> None:
        config = make_config(
            on_table(
                "orders",
                self.FK,
                "foreign_key: { column: customer_id, ref_table: orders, ref_column: order_id }",
            )
        )
        first, second = run_checks(config, now=NOW).results
        assert first.check_key != second.check_key

    def test_options_are_required(self) -> None:
        with pytest.raises(ValidationError):
            ForeignKeyCheck(type="foreign_key", column="customer_id")  # type: ignore[call-arg]
