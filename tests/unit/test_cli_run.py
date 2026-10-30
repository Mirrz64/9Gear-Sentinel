from pathlib import Path

from typer.testing import CliRunner

from sentinel.cli import app

runner = CliRunner()


def write_config(tmp_path: Path, demo_db: Path, checks: str) -> Path:
    path = tmp_path / "sentinel.yml"
    path.write_text(
        "version: 1\n"
        "sources:\n"
        "  local:\n"
        "    type: sqlite\n"
        f"    url: sqlite:///{demo_db.as_posix()}\n"
        "store:\n"
        f"  url: sqlite:///{(tmp_path / 'store' / 'results.db').as_posix()}\n"
        "tables:\n"
        "  - source: local\n"
        "    table: orders\n"
        "    checks:\n" + checks,
        encoding="utf-8",
    )
    return path


def test_run_with_failures_exits_1(tmp_path: Path, demo_db: Path) -> None:
    config = write_config(tmp_path, demo_db, "      - unique: { columns: [order_id] }\n")
    result = runner.invoke(app, ["run", "-c", str(config)])
    assert result.exit_code == 1, result.output
    assert "FAIL" in result.output
    assert "1 check, 1 failed" in result.output


def test_run_all_passing_exits_0(tmp_path: Path, demo_db: Path) -> None:
    config = write_config(tmp_path, demo_db, "      - row_count: { min: 1 }\n")
    result = runner.invoke(app, ["run", "-c", str(config)])
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output


def test_run_saves_results_and_history_shows_them(tmp_path: Path, demo_db: Path) -> None:
    config = write_config(
        tmp_path,
        demo_db,
        "      - row_count: { min: 1 }\n      - unique: { columns: [order_id] }\n",
    )
    runner.invoke(app, ["run", "-c", str(config)])
    runner.invoke(app, ["run", "-c", str(config)])
    assert (tmp_path / "store" / "results.db").is_file()

    result = runner.invoke(app, ["history", "-c", str(config)])
    assert result.exit_code == 0, result.output
    assert result.output.count("unique(order_id)") == 2
    assert result.output.count("row_count") == 2

    result = runner.invoke(app, ["history", "-c", str(config), "--check", "unique", "-n", "1"])
    assert result.output.count("unique(order_id)") == 1
    assert "row_count" not in result.output


def test_row_count_change_across_runs(tmp_path: Path, demo_db: Path) -> None:
    import sqlite3

    config = write_config(tmp_path, demo_db, "      - row_count_change: { max_drop_pct: 10 }\n")
    first = runner.invoke(app, ["run", "-c", str(config)])
    assert first.exit_code == 0, first.output
    assert "baseline" in first.output

    conn = sqlite3.connect(demo_db)
    conn.execute("DELETE FROM orders WHERE order_id > 50")
    conn.commit()
    conn.close()

    second = runner.invoke(app, ["run", "-c", str(config)])
    assert second.exit_code == 1, second.output
    assert "dropped" in second.output


def test_no_store_flag_saves_nothing(tmp_path: Path, demo_db: Path) -> None:
    config = write_config(tmp_path, demo_db, "      - row_count: { min: 1 }\n")
    runner.invoke(app, ["run", "-c", str(config), "--no-store"])
    assert not (tmp_path / "store" / "results.db").exists()


def test_history_before_any_run(tmp_path: Path, demo_db: Path) -> None:
    config = write_config(tmp_path, demo_db, "      - row_count: { min: 1 }\n")
    result = runner.invoke(app, ["history", "-c", str(config)])
    assert result.exit_code == 0
    assert "no results yet" in result.output


def test_run_with_no_matching_checks_exits_2(tmp_path: Path, demo_db: Path) -> None:
    config = write_config(tmp_path, demo_db, "      - row_count: { min: 1 }\n")
    result = runner.invoke(app, ["run", "-c", str(config), "--check", "freshness"])
    assert result.exit_code == 2


def test_test_connection_ok(tmp_path: Path, demo_db: Path) -> None:
    config = write_config(tmp_path, demo_db, "      - row_count: { min: 1 }\n")
    result = runner.invoke(app, ["test-connection", "-c", str(config)])
    assert result.exit_code == 0, result.output
    assert "OK" in result.output


def test_test_connection_unknown_source(tmp_path: Path, demo_db: Path) -> None:
    config = write_config(tmp_path, demo_db, "      - row_count: { min: 1 }\n")
    result = runner.invoke(app, ["test-connection", "-c", str(config), "-s", "nope"])
    assert result.exit_code == 2
