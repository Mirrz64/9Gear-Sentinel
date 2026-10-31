"""Failure messages include a few offending values, and polish from v0.1.1."""

from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from sentinel.checks.accepted_values import describe_sample as describe_values
from sentinel.checks.base import show_value
from sentinel.checks.unique import describe_sample as describe_keys
from sentinel.cli import app
from sentinel.config import SentinelConfig
from sentinel.config.models import AcceptedValuesCheck, UniqueCheck
from sentinel.runner import run_checks
from tests.conftest import NOW

MakeConfig = Callable[[str], SentinelConfig]
runner = CliRunner()


def checks(*lines: str) -> str:
    return "  - source: local\n    table: orders\n    checks:\n" + "".join(
        f"      - {line}\n" for line in lines
    )


def test_unique_failure_names_the_duplicate_keys(make_config: MakeConfig) -> None:
    config = make_config(checks("unique: { columns: [order_id] }"))
    (result,) = run_checks(config, now=NOW).results
    assert result.status == "FAIL"
    assert result.message == "2 duplicate keys in (order_id); e.g. 5, 7"


def test_composite_keys_are_shown_as_tuples(make_config: MakeConfig) -> None:
    config = make_config(checks("unique: { columns: [order_id, customer_id] }"))
    (result,) = run_checks(config, now=NOW).results
    assert result.message.endswith("e.g. (5, 5), (7, 7)")


def test_accepted_values_failure_names_the_values(make_config: MakeConfig) -> None:
    config = make_config(checks("accepted_values: { column: order_id, values: [1, 2, 3] }"))
    (result,) = run_checks(config, now=NOW).results
    # 5 and 7 appear twice, so they come first; then the rest in order
    assert result.message.endswith("; found 5, 7, 4, 6, 8")


def test_passing_checks_have_no_examples(make_config: MakeConfig) -> None:
    config = make_config(
        "  - source: local\n    table: customers\n    checks:\n      - unique: { columns: [id] }\n"
    )
    (result,) = run_checks(config, now=NOW).results
    assert result.status == "PASS"
    assert result.message == "(id) is unique"


def test_describe_helpers() -> None:
    assert show_value("paid") == "'paid'"
    assert show_value(42) == "42"
    assert show_value("x" * 60).endswith("…") and len(show_value("x" * 60)) == 40
    unique = UniqueCheck(type="unique", columns=["a", "b"])
    assert describe_keys(unique, [("x", 1)]) == "e.g. ('x', 1)"
    values = AcceptedValuesCheck(type="accepted_values", column="s", values=["a"])
    assert describe_values(values, [("zz",), ("yy",)]) == "found 'zz', 'yy'"


def test_validate_uses_proper_plurals(tmp_path: Path, demo_db: Path) -> None:
    config = tmp_path / "sentinel.yml"
    text = (
        "version: 1\nsources:\n  local:\n    type: sqlite\n"
        f"    url: sqlite:///{demo_db.as_posix()}\ntables:\n"
    )
    config.write_text(text + checks("row_count: { min: 1 }"), encoding="utf-8")
    result = runner.invoke(app, ["validate", "-c", str(config)])
    assert "1 source, 1 table, 1 check" in result.output


def test_init_suggests_test_connection(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert "sentinel test-connection" in result.output
    assert "Change the table and column names" in (tmp_path / "sentinel.yml").read_text(
        encoding="utf-8"
    )
