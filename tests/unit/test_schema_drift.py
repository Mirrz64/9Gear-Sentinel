import sqlite3
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from sentinel.checks.schema_drift import diff, evaluate
from sentinel.cli import app
from sentinel.config import SentinelConfig
from sentinel.config.models import SchemaDriftCheck
from sentinel.runner import run_checks
from tests.conftest import NOW

MakeConfig = Callable[[str], SentinelConfig]
runner = CliRunner()

BASE = (("id", "INTEGER"), ("email", "TEXT"), ("created_at", "TEXT"))


class TestDiff:
    def test_no_changes(self) -> None:
        assert diff(BASE, BASE) == []

    def test_added_removed_and_retyped(self) -> None:
        current = (("id", "BIGINT"), ("created_at", "TEXT"), ("country", "TEXT"))
        assert diff(BASE, current) == [
            "added country (TEXT)",
            "removed email",
            "id changed INTEGER -> BIGINT",
        ]

    def test_ignored_columns(self) -> None:
        current = (*BASE, ("loaded_at", "TEXT"))
        assert diff(BASE, current, ignore=["loaded_at"]) == []


class TestEvaluate:
    spec = SchemaDriftCheck(type="schema_drift")

    def test_no_baseline_passes(self) -> None:
        result = evaluate(self.spec, BASE, None)
        assert result.passed
        assert "recorded 3 columns" in result.message

    def test_unchanged_passes(self) -> None:
        assert evaluate(self.spec, BASE, BASE).passed

    def test_drift_fails_and_counts_changes(self) -> None:
        result = evaluate(self.spec, BASE[:1], BASE)
        assert not result.passed
        assert result.observed == 2
        assert result.message.startswith("2 changes: removed email; removed created_at")

    def test_long_change_lists_are_shortened(self) -> None:
        current = tuple((f"c{n}", "TEXT") for n in range(8))
        assert "+6 more" in evaluate(self.spec, current, BASE).message


def test_runner_records_first_baseline(make_config: MakeConfig) -> None:
    config = make_config(
        "  - source: local\n    table: customers\n    checks:\n      - schema_drift: {}\n"
    )
    report = run_checks(config, now=NOW)
    assert report.results[0].status == "PASS"
    (snapshot,) = report.new_snapshots
    assert snapshot.table == "customers"
    assert [name for name, _ in snapshot.columns] == ["id", "email", "created_at"]


def test_runner_reports_missing_table(make_config: MakeConfig) -> None:
    config = make_config(
        "  - source: local\n    table: no_such_table\n    checks:\n      - schema_drift: {}\n"
    )
    result = run_checks(config, now=NOW).results[0]
    assert result.status == "ERROR"
    assert "not found" in result.message


def write_config(tmp_path: Path, demo_db: Path) -> Path:
    path = tmp_path / "sentinel.yml"
    path.write_text(
        "version: 1\n"
        "sources:\n"
        "  local:\n"
        "    type: sqlite\n"
        f"    url: sqlite:///{demo_db.as_posix()}\n"
        "store:\n"
        f"  url: sqlite:///{(tmp_path / 'results.db').as_posix()}\n"
        "tables:\n"
        "  - source: local\n"
        "    table: customers\n"
        "    checks:\n"
        "      - schema_drift: {}\n",
        encoding="utf-8",
    )
    return path


def test_drift_lifecycle_through_the_cli(tmp_path: Path, demo_db: Path) -> None:
    config = str(write_config(tmp_path, demo_db))

    first = runner.invoke(app, ["run", "-c", config])
    assert first.exit_code == 0, first.output
    assert "no baseline yet" in first.output

    second = runner.invoke(app, ["run", "-c", config])
    assert "schema unchanged" in second.output

    conn = sqlite3.connect(demo_db)
    conn.execute("ALTER TABLE customers ADD COLUMN country TEXT")
    conn.commit()
    conn.close()

    drifted = runner.invoke(app, ["run", "-c", config])
    assert drifted.exit_code == 1, drifted.output
    assert "added country (TEXT)" in drifted.output

    still_drifted = runner.invoke(app, ["run", "-c", config])
    assert still_drifted.exit_code == 1

    accepted = runner.invoke(app, ["snapshot-schema", "-c", config])
    assert accepted.exit_code == 0, accepted.output
    assert "customers (4 columns)" in accepted.output

    after = runner.invoke(app, ["run", "-c", config])
    assert after.exit_code == 0, after.output
    assert "schema unchanged" in after.output


def test_snapshot_schema_needs_targets(tmp_path: Path, demo_db: Path) -> None:
    config = tmp_path / "sentinel.yml"
    config.write_text(
        write_config(tmp_path, demo_db)
        .read_text(encoding="utf-8")
        .replace("schema_drift: {}", "row_count: { min: 1 }"),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["snapshot-schema", "-c", str(config)])
    assert result.exit_code == 2

    with_table = runner.invoke(app, ["snapshot-schema", "-c", str(config), "-t", "customers"])
    assert with_table.exit_code == 0, with_table.output
