"""Runs only when SENTINEL_TEST_PG_URL points at a Postgres (CI sets it; locally use Docker)."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text

from sentinel.config import load_config
from sentinel.runner import run_checks

PG_URL = os.environ.get("SENTINEL_TEST_PG_URL", "")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not PG_URL, reason="set SENTINEL_TEST_PG_URL to run Postgres tests"),
]


@pytest.fixture(scope="module")
def pg() -> Iterator[Engine]:
    engine = create_engine(PG_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS sentinel_it CASCADE"))
        conn.execute(text("CREATE SCHEMA sentinel_it"))
        conn.execute(
            text(
                "CREATE TABLE sentinel_it.orders "
                "(order_id int, customer_id int, updated_at timestamptz, created_on date)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO sentinel_it.orders "
                "SELECT g, CASE WHEN g % 10 = 0 THEN NULL ELSE g END, "
                "now() - interval '2 days', current_date - 2 "
                "FROM generate_series(1, 100) AS g"
            )
        )
        conn.execute(
            text("INSERT INTO sentinel_it.orders VALUES (1, 1, now() - interval '2 days', NULL)")
        )
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA sentinel_it CASCADE"))
    engine.dispose()


def test_checks_against_postgres(pg: Engine, tmp_path: Path) -> None:
    config_path = tmp_path / "sentinel.yml"
    config_path.write_text(
        f"""\
version: 1
sources:
  pg:
    type: postgres
    url: {PG_URL}
tables:
  - source: pg
    table: sentinel_it.orders
    checks:
      - freshness: {{ column: updated_at, max_age: 6h }}
      - freshness: {{ column: updated_at, max_age: 3d, name: fresh_enough }}
      - freshness: {{ column: created_on, max_age: 4d, name: date_column }}
      - row_count: {{ min: 101, max: 101 }}
      - null_rate: {{ column: customer_id, max_pct: 5 }}
      - not_null: {{ column: customer_id }}
      - unique: {{ columns: [order_id] }}
      - unique: {{ columns: [order_id, customer_id], name: composite_key }}
      - accepted_values: {{ column: order_id, values: [1, 2, 3] }}
      - custom_sql:
          name: null_customers
          sql: select * from sentinel_it.orders where customer_id is null
""",
        encoding="utf-8",
    )
    report = run_checks(load_config(config_path, environ={}))
    statuses = {r.label: r.status for r in report.results}
    assert statuses == {
        "freshness(updated_at)": "FAIL",
        "fresh_enough": "PASS",
        "date_column": "PASS",
        "row_count": "PASS",
        "null_rate(customer_id)": "FAIL",
        "not_null(customer_id)": "FAIL",
        "unique(order_id)": "FAIL",
        "composite_key": "FAIL",
        "accepted_values(order_id)": "FAIL",
        "null_customers": "FAIL",
    }
    assert report.exit_code == 1


def test_missing_table_is_an_error(pg: Engine, tmp_path: Path) -> None:
    config_path = tmp_path / "sentinel.yml"
    config_path.write_text(
        f"version: 1\nsources:\n  pg:\n    type: postgres\n    url: {PG_URL}\n"
        "tables:\n  - source: pg\n    table: sentinel_it.missing\n"
        "    checks:\n      - row_count: { min: 1 }\n",
        encoding="utf-8",
    )
    report = run_checks(load_config(config_path, environ={}))
    assert report.results[0].status == "ERROR"
    assert "missing" in report.results[0].message
    assert report.exit_code == 2


def test_schema_drift_against_postgres(pg: Engine, tmp_path: Path) -> None:
    from sentinel.store import ResultStore

    config_path = tmp_path / "sentinel.yml"
    config_path.write_text(
        f"version: 1\nsources:\n  pg:\n    type: postgres\n    url: {PG_URL}\n"
        "tables:\n  - source: pg\n    table: sentinel_it.orders\n"
        "    checks:\n      - schema_drift: {}\n",
        encoding="utf-8",
    )
    config = load_config(config_path, environ={})
    store = ResultStore.open(f"sqlite:///{(tmp_path / 'results.db').as_posix()}")
    try:
        first = run_checks(config, schema_baseline=store.latest_snapshot)
        store.save(first)
        assert first.results[0].status == "PASS"

        with pg.begin() as conn:
            conn.execute(text("ALTER TABLE sentinel_it.orders ADD COLUMN discount numeric(5, 2)"))
        try:
            second = run_checks(config, schema_baseline=store.latest_snapshot)
            assert second.results[0].status == "FAIL"
            assert "added discount" in second.results[0].message
        finally:
            with pg.begin() as conn:
                conn.execute(text("ALTER TABLE sentinel_it.orders DROP COLUMN discount"))
    finally:
        store.close()
