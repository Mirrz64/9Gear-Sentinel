from pathlib import Path

import pytest

from sentinel.config import ConfigError, load_config
from sentinel.config.models import FreshnessCheck, RowCountCheck

ENV = {"WAREHOUSE_URL": "postgresql+psycopg://u:p@localhost:5432/db"}

VALID = """\
version: 1
sources:
  warehouse:
    type: postgres
    url: ${WAREHOUSE_URL}
tables:
  - source: warehouse
    table: analytics.orders
    checks:
      - freshness: { column: updated_at, max_age: 6h }
      - row_count: { min: 1 }
      - schema_drift:
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "sentinel.yml"
    path.write_text(text, encoding="utf-8")
    return path


def issues_for(path: Path, **kwargs: object) -> list[str]:
    with pytest.raises(ConfigError) as info:
        load_config(path, environ=ENV, **kwargs)  # type: ignore[arg-type]
    return [str(issue) for issue in info.value.issues]


def test_valid_config_loads(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, VALID), environ=ENV)
    assert config.sources["warehouse"].url == ENV["WAREHOUSE_URL"]
    checks = config.tables[0].checks
    assert isinstance(checks[0], FreshnessCheck)
    assert checks[0].max_age.total_seconds() == 6 * 3600
    assert isinstance(checks[1], RowCountCheck)
    assert config.check_count() == 3
    assert config.store.url.startswith("sqlite:///")


def test_missing_env_var_reports_line(tmp_path: Path) -> None:
    path = write(tmp_path, VALID)
    with pytest.raises(ConfigError) as info:
        load_config(path, environ={})
    (issue,) = info.value.issues
    assert issue.line == 5
    assert issue.path == "sources.warehouse.url"
    assert "WAREHOUSE_URL" in issue.message


def test_skip_env_keeps_placeholder(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, VALID), environ={}, require_env=False)
    assert config.sources["warehouse"].url == "${WAREHOUSE_URL}"


def test_env_default_value(tmp_path: Path) -> None:
    text = VALID.replace("${WAREHOUSE_URL}", "${WAREHOUSE_URL:-sqlite:///local.db}")
    config = load_config(write(tmp_path, text), environ={})
    assert config.sources["warehouse"].url == "sqlite:///local.db"


def test_dotenv_file_is_read(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("WAREHOUSE_URL=postgresql://from-dotenv\n", encoding="utf-8")
    config = load_config(write(tmp_path, VALID), environ={})
    assert config.sources["warehouse"].url == "postgresql://from-dotenv"


def test_bad_duration_points_at_its_line(tmp_path: Path) -> None:
    text = VALID.replace(
        "      - freshness: { column: updated_at, max_age: 6h }\n",
        "      - freshness:\n          column: updated_at\n          max_age: 6x\n",
    )
    (message,) = issues_for(write(tmp_path, text))
    assert ":12 " in message
    assert "tables[0].checks[0].freshness.max_age" in message
    assert "invalid duration" in message


def test_unknown_check_type(tmp_path: Path) -> None:
    text = VALID.replace("- row_count: { min: 1 }", "- row_cnt: { min: 1 }")
    (message,) = issues_for(write(tmp_path, text))
    assert ":11 " in message
    assert "unknown check type 'row_cnt'" in message


def test_typo_in_field_name(tmp_path: Path) -> None:
    text = VALID.replace("{ min: 1 }", "{ minimum: 1 }")
    messages = issues_for(write(tmp_path, text))
    assert any("minimum" in m and "unknown field" in m for m in messages)


def test_row_count_needs_a_bound(tmp_path: Path) -> None:
    text = VALID.replace("{ min: 1 }", "{}")
    (message,) = issues_for(write(tmp_path, text))
    assert "set at least one of min or max" in message


def test_undefined_source(tmp_path: Path) -> None:
    text = VALID.replace("  - source: warehouse", "  - source: wherehouse")
    (message,) = issues_for(write(tmp_path, text))
    assert ":7 " in message
    assert "source 'wherehouse' is not defined" in message


def test_yaml_syntax_error(tmp_path: Path) -> None:
    (message,) = issues_for(write(tmp_path, "version: 1\nsources: [unclosed\n"))
    assert "invalid YAML" in message


def test_missing_file(tmp_path: Path) -> None:
    (message,) = issues_for(tmp_path / "nope.yml")
    assert "sentinel init" in message
