"""`sentinel run --format json` prints one parseable document and nothing else on stdout."""

import json
from pathlib import Path

from typer.testing import CliRunner

from sentinel.cli import app
from tests.unit.test_cli_run import write_config

runner = CliRunner()


def test_json_output_has_totals_and_one_entry_per_check(tmp_path: Path, demo_db: Path) -> None:
    config = write_config(
        tmp_path,
        demo_db,
        "      - row_count: { min: 1 }\n      - unique: { columns: [order_id] }\n",
    )
    result = runner.invoke(app, ["run", "-c", str(config), "--format", "json"])
    assert result.exit_code == 1, result.output

    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["exit_code"] == 1
    assert payload["counts"] == {"pass": 1, "fail": 1, "warn": 0, "error": 0, "skip": 0}
    assert payload["started_at"] <= payload["finished_at"]

    by_check = {entry["check"]: entry for entry in payload["results"]}
    assert set(by_check) == {"row_count", "unique(order_id)"}
    failed = by_check["unique(order_id)"]
    assert failed["status"] == "FAIL"
    assert failed["type"] == "unique"
    assert failed["table"] == "orders"
    assert failed["severity"] == "error"
    assert failed["observed"] == 2
    assert "duplicate" in failed["message"]


def test_json_output_has_no_table_text(tmp_path: Path, demo_db: Path) -> None:
    config = write_config(tmp_path, demo_db, "      - row_count: { min: 1 }\n")
    result = runner.invoke(app, ["run", "-c", str(config), "--format", "json", "--no-store"])
    assert result.exit_code == 0, result.output
    assert result.stdout.lstrip().startswith("{")
    assert "1 check, 1 passed" not in result.stdout
    assert json.loads(result.stdout)["status"] == "passed"


def test_short_flag_and_default_format(tmp_path: Path, demo_db: Path) -> None:
    config = write_config(tmp_path, demo_db, "      - row_count: { min: 1 }\n")
    as_json = runner.invoke(app, ["run", "-c", str(config), "-f", "json", "--no-store"])
    assert json.loads(as_json.stdout)["counts"]["pass"] == 1

    as_table = runner.invoke(app, ["run", "-c", str(config), "--no-store"])
    assert "1 check, 1 passed" in as_table.output


def test_unknown_format_is_rejected(tmp_path: Path, demo_db: Path) -> None:
    config = write_config(tmp_path, demo_db, "      - row_count: { min: 1 }\n")
    result = runner.invoke(app, ["run", "-c", str(config), "--format", "xml"])
    assert result.exit_code == 2
