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
    assert "1 checks, 1 failed" in result.output


def test_run_all_passing_exits_0(tmp_path: Path, demo_db: Path) -> None:
    config = write_config(tmp_path, demo_db, "      - row_count: { min: 1 }\n")
    result = runner.invoke(app, ["run", "-c", str(config)])
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output


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
