"""Runs only when SENTINEL_TEST_MYSQL_URL points at a MySQL 8 database (CI sets it).

Locally: docker compose up -d mysql, then
SENTINEL_TEST_MYSQL_URL=mysql+pymysql://sentinel:sentinel@localhost:3307/analytics pytest
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text

from sentinel.config import load_config
from sentinel.runner import run_checks

MYSQL_URL = os.environ.get("SENTINEL_TEST_MYSQL_URL", "")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not MYSQL_URL, reason="set SENTINEL_TEST_MYSQL_URL to run MySQL tests"),
]

TABLE = "sentinel_it_orders"


@pytest.fixture(scope="module")
def mysql() -> Iterator[Engine]:
    pytest.importorskip("pymysql")
    engine = create_engine(MYSQL_URL)
    # DATETIME has no time zone; Sentinel reads it as UTC, so store UTC.
    updated = (datetime.now(UTC) - timedelta(days=2)).replace(tzinfo=None, microsecond=0)
    rows = [{"o": i, "c": None if i % 10 == 0 else i, "u": updated} for i in range(1, 101)] + [
        {"o": 1, "c": 1, "u": updated}
    ]
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        conn.execute(
            text(f"CREATE TABLE {TABLE} (order_id INT, customer_id INT, updated_at DATETIME)")
        )
        conn.execute(
            text(f"INSERT INTO {TABLE} (order_id, customer_id, updated_at) VALUES (:o, :c, :u)"),
            rows,
        )
    yield engine
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE {TABLE}"))
    engine.dispose()


def test_checks_against_mysql(mysql: Engine, tmp_path: Path) -> None:
    config_path = tmp_path / "sentinel.yml"
    config_path.write_text(
        f"""\
version: 1
sources:
  my:
    type: mysql
    url: {MYSQL_URL}
tables:
  - source: my
    table: {TABLE}
    checks:
      - freshness: {{ column: updated_at, max_age: 6h, name: stale }}
      - freshness: {{ column: updated_at, max_age: 3d, name: fresh_enough }}
      - row_count: {{ min: 101, max: 101 }}
      - null_rate: {{ column: customer_id, max_pct: 5 }}
      - not_null: {{ column: customer_id }}
      - unique: {{ columns: [order_id] }}
      - accepted_values: {{ column: order_id, values: [1, 2, 3] }}
      - schema_drift: {{}}
""",
        encoding="utf-8",
    )
    report = run_checks(load_config(config_path, environ={}))
    statuses = {r.label: r.status for r in report.results}
    errors = {r.label: r.message for r in report.results if r.status == "ERROR"}
    assert statuses == {
        "stale": "FAIL",
        "fresh_enough": "PASS",
        "row_count": "PASS",
        "null_rate(customer_id)": "FAIL",
        "not_null(customer_id)": "FAIL",
        "unique(order_id)": "FAIL",
        "accepted_values(order_id)": "FAIL",
        "schema_drift": "PASS",
    }, errors
