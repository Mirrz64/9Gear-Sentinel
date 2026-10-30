from pathlib import Path

from typer.testing import CliRunner

from sentinel import __version__
from sentinel.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_init_then_validate(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "sentinel.yml").is_file()
    assert (tmp_path / ".env.example").is_file()

    result = runner.invoke(
        app, ["validate", "--config", str(tmp_path / "sentinel.yml"), "--skip-env"]
    )
    assert result.exit_code == 0, result.output
    assert "is valid" in result.output


def test_init_refuses_to_overwrite(tmp_path: Path) -> None:
    runner.invoke(app, ["init", str(tmp_path)])
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 2


def test_validate_reports_problems(tmp_path: Path) -> None:
    config = tmp_path / "sentinel.yml"
    config.write_text("version: 2\n", encoding="utf-8")
    result = runner.invoke(app, ["validate", "--config", str(config), "--skip-env"])
    assert result.exit_code == 2
