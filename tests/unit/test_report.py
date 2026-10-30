from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sentinel.cli import app
from sentinel.config import SentinelConfig
from sentinel.report import render_report
from sentinel.runner import run_checks
from sentinel.store import ResultStore
from tests.conftest import NOW

MakeConfig = Callable[[str], SentinelConfig]
runner = CliRunner()

CHECKS = (
    "  - source: local\n    table: orders\n    checks:\n"
    "      - row_count: { min: 1 }\n"
    "      - unique: { columns: [order_id] }\n"
    "      - custom_sql:\n"
    "          name: odd <name> & co\n"
    "          sql: select 1 where 1 = 0\n"
)


def test_latest_run_and_trends(tmp_path: Path, make_config: MakeConfig) -> None:
    store = ResultStore.open(f"sqlite:///{(tmp_path / 'r.db').as_posix()}")
    try:
        assert store.latest_run() is None
        config = make_config(CHECKS)
        for _ in range(3):
            store.save(run_checks(config, now=NOW))
        latest = store.latest_run()
    finally:
        store.close()

    assert latest is not None
    assert latest.status == "failed"
    assert [r.label for r in latest.results] == ["row_count", "unique(order_id)", "odd <name> & co"]
    assert latest.trends["orders:unique(order_id)"] == ["FAIL", "FAIL", "FAIL"]
    assert latest.trends["orders:row_count"] == ["PASS", "PASS", "PASS"]


def test_rendered_html_is_escaped_and_complete(tmp_path: Path, make_config: MakeConfig) -> None:
    store = ResultStore.open(f"sqlite:///{(tmp_path / 'r.db').as_posix()}")
    try:
        store.save(run_checks(make_config(CHECKS), now=NOW))
        latest = store.latest_run()
    finally:
        store.close()
    assert latest is not None

    page = render_report(latest)
    assert page.startswith("<!doctype html>")
    assert "odd &lt;name&gt; &amp; co" in page
    assert "odd <name>" not in page
    assert page.index("unique(order_id)") < page.index("row_count")  # failures first
    assert "prefers-color-scheme: dark" in page


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
        "    table: orders\n"
        "    checks:\n"
        "      - unique: { columns: [order_id] }\n"
        "      - accepted_values: { column: order_id, values: [1, 2] }\n",
        encoding="utf-8",
    )
    return path


def test_report_command(tmp_path: Path, demo_db: Path) -> None:
    config = str(write_config(tmp_path, demo_db))
    out = tmp_path / "out" / "report.html"

    empty = runner.invoke(app, ["report", "-c", config, "--out", str(out)])
    assert empty.exit_code == 2

    runner.invoke(app, ["run", "-c", config])
    result = runner.invoke(app, ["report", "-c", config, "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "unique(order_id)" in out.read_text(encoding="utf-8")


def test_dry_run_prints_sql_and_saves_nothing(tmp_path: Path, demo_db: Path) -> None:
    config = str(write_config(tmp_path, demo_db))
    result = runner.invoke(app, ["run", "-c", config, "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "-- orders  unique(order_id)" in result.output
    assert "GROUP BY order_id" in result.output
    assert "NOT IN (1, 2)" in result.output
    assert not (tmp_path / "results.db").exists()


def test_watch_runs_on_schedule(
    tmp_path: Path, demo_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [datetime(2026, 11, 2, 10, 17, 30)]

    def advance(seconds: float) -> None:
        clock[0] += timedelta(seconds=seconds)

    monkeypatch.setattr("sentinel.cli._now", lambda: clock[0])
    monkeypatch.setattr("sentinel.cli._sleep", advance)

    config = str(write_config(tmp_path, demo_db))
    result = runner.invoke(app, ["watch", "-c", config, "--cron", "*/5 * * * *", "--max-runs", "2"])
    assert result.exit_code == 0, result.output
    assert "next run at 2026-11-02 10:20" in result.output
    assert "next run at 2026-11-02 10:25" in result.output

    history = runner.invoke(app, ["history", "-c", config, "--check", "unique"])
    assert history.output.count("unique(order_id)") == 2


def test_watch_needs_a_schedule(tmp_path: Path, demo_db: Path) -> None:
    config = str(write_config(tmp_path, demo_db))
    assert runner.invoke(app, ["watch", "-c", config]).exit_code == 2
    bad = runner.invoke(app, ["watch", "-c", config, "--cron", "61 * * * *"])
    assert bad.exit_code == 2
