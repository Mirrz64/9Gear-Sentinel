"""DuckDB runs in-process, so these tests need no service, only the duckdb extra."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

pytest.importorskip("duckdb_engine")

from sentinel.config import load_config  # noqa: E402
from sentinel.runner import run_checks  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture
def duck_path(tmp_path: Path) -> Path:
    path = tmp_path / "warehouse.duckdb"
    engine = create_engine(f"duckdb:///{path.as_posix()}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE orders AS SELECT i AS order_id, "
                "CASE WHEN i % 10 = 0 THEN NULL ELSE i END AS customer_id, "
                "now() - INTERVAL 2 DAY AS updated_at "
                "FROM range(1, 101) AS t(i)"
            )
        )
        conn.execute(text("INSERT INTO orders VALUES (1, 1, now() - INTERVAL 2 DAY)"))
    engine.dispose()
    return path


def test_checks_against_duckdb(tmp_path: Path, duck_path: Path) -> None:
    config_path = tmp_path / "sentinel.yml"
    config_path.write_text(
        f"""\
version: 1
sources:
  duck:
    type: duckdb
    url: duckdb:///{duck_path.as_posix()}
tables:
  - source: duck
    table: orders
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
    assert statuses == {
        "stale": "FAIL",
        "fresh_enough": "PASS",
        "row_count": "PASS",
        "null_rate(customer_id)": "FAIL",
        "not_null(customer_id)": "FAIL",
        "unique(order_id)": "FAIL",
        "accepted_values(order_id)": "FAIL",
        "schema_drift": "PASS",
    }
