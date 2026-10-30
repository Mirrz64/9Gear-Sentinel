from collections.abc import Callable

from sentinel.config import SentinelConfig
from sentinel.runner import Selection, run_checks
from tests.conftest import NOW

MakeConfig = Callable[[str], SentinelConfig]

ORDERS_AND_CUSTOMERS = """\
  - source: local
    table: orders
    tags: [core]
    checks:
      - freshness: { column: updated_at, max_age: 6h }
      - row_count: { min: 1 }
      - null_rate: { column: customer_id, max_pct: 1, severity: warn }
      - not_null: { column: customer_id }
      - unique: { columns: [order_id] }
      - accepted_values: { column: order_id, values: [1] }
  - source: local
    table: customers
    checks:
      - freshness: { column: created_at, max_age: 1d }
      - row_count: { min: 50, max: 50 }
      - not_null: { column: email }
      - unique: { columns: [id] }
"""


def statuses(config: SentinelConfig, selection: Selection | None = None) -> dict[str, str]:
    report = run_checks(config, selection, now=NOW)
    return {f"{r.table}:{r.label}": r.status for r in report.results}


def test_full_run_against_sqlite(make_config: MakeConfig) -> None:
    result = statuses(make_config(ORDERS_AND_CUSTOMERS))
    assert result == {
        "orders:freshness(updated_at)": "FAIL",
        "orders:row_count": "PASS",
        "orders:null_rate(customer_id)": "WARN",
        "orders:not_null(customer_id)": "FAIL",
        "orders:unique(order_id)": "FAIL",
        "orders:accepted_values(order_id)": "FAIL",
        "customers:freshness(created_at)": "PASS",
        "customers:row_count": "PASS",
        "customers:not_null(email)": "PASS",
        "customers:unique(id)": "PASS",
    }


def test_observed_values(make_config: MakeConfig) -> None:
    report = run_checks(make_config(ORDERS_AND_CUSTOMERS), now=NOW)
    by_label = {f"{r.table}:{r.label}": r for r in report.results}
    assert by_label["orders:row_count"].observed == 102
    assert by_label["orders:unique(order_id)"].observed == 2
    assert by_label["orders:not_null(customer_id)"].observed == 10


def test_exit_codes(make_config: MakeConfig) -> None:
    failing = run_checks(make_config(ORDERS_AND_CUSTOMERS), now=NOW)
    assert failing.exit_code == 1

    warn_only = make_config(
        "  - source: local\n    table: orders\n    checks:\n"
        "      - null_rate: { column: customer_id, max_pct: 1, severity: warn }\n"
    )
    assert run_checks(warn_only, now=NOW).exit_code == 0


def test_where_filter(make_config: MakeConfig) -> None:
    config = make_config(
        "  - source: local\n    table: orders\n    checks:\n"
        "      - not_null: { column: customer_id, where: 'order_id < 10' }\n"
    )
    assert run_checks(config, now=NOW).results[0].status == "PASS"


def test_missing_column_is_an_error(make_config: MakeConfig) -> None:
    config = make_config(
        "  - source: local\n    table: orders\n    checks:\n"
        "      - not_null: { column: no_such_column }\n"
    )
    report = run_checks(config, now=NOW)
    assert report.results[0].status == "ERROR"
    assert "no_such_column" in report.results[0].message
    assert report.exit_code == 2


def test_empty_table_freshness_fails(make_config: MakeConfig) -> None:
    config = make_config(
        "  - source: local\n    table: empty_table\n    checks:\n"
        "      - freshness: { column: updated_at, max_age: 1h }\n"
        "      - row_count: { min: 1 }\n"
    )
    assert [r.status for r in run_checks(config, now=NOW).results] == ["FAIL", "FAIL"]


def test_selection_filters(make_config: MakeConfig) -> None:
    config = make_config(ORDERS_AND_CUSTOMERS)
    assert set(statuses(config, Selection(tables=["customers"]))) == {
        "customers:freshness(created_at)",
        "customers:row_count",
        "customers:not_null(email)",
        "customers:unique(id)",
    }
    assert set(statuses(config, Selection(check_types=["unique"]))) == {
        "orders:unique(order_id)",
        "customers:unique(id)",
    }
    assert len(statuses(config, Selection(tags=["core"]))) == 6


def test_custom_sql(make_config: MakeConfig) -> None:
    config = make_config(
        "  - source: local\n    table: orders\n    checks:\n"
        "      - custom_sql:\n"
        "          name: null_customers\n"
        "          sql: select * from orders where customer_id is null;\n"
        "      - custom_sql:\n"
        "          name: negative_ids\n"
        "          sql: select * from orders where order_id < 0\n"
    )
    results = run_checks(config, now=NOW).results
    assert [(r.label, r.status, r.observed) for r in results] == [
        ("null_customers", "FAIL", 10),
        ("negative_ids", "PASS", 0),
    ]


def test_row_count_change_uses_previous_lookup(make_config: MakeConfig) -> None:
    config = make_config(
        "  - source: local\n    table: orders\n    checks:\n"
        "      - row_count_change: { max_drop_pct: 10 }\n"
    )
    first = run_checks(config, now=NOW).results[0]
    assert first.status == "PASS" and "baseline" in first.message

    baseline = {first.check_key: 200.0}
    second = run_checks(config, now=NOW, previous=baseline.get).results[0]
    assert second.status == "FAIL"
    assert "dropped 49%" in second.message


def test_check_key_ignores_thresholds_but_not_columns() -> None:
    from sentinel.config.models import NullRateCheck
    from sentinel.runner import check_key

    loose = NullRateCheck(type="null_rate", column="a", max_pct=5)
    strict = NullRateCheck(type="null_rate", column="a", max_pct=1, severity="warn")
    other = NullRateCheck(type="null_rate", column="b", max_pct=5)
    assert check_key("src", "t", loose) == check_key("src", "t", strict)
    assert check_key("src", "t", loose) != check_key("src", "t", other)
    assert check_key("src", "t", loose) != check_key("src", "t2", loose)
