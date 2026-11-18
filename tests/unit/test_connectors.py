import pytest

from sentinel.config.models import Source
from sentinel.connectors import ConnectorError, create_source_engine
from sentinel.connectors.base import _INSTALL_HINTS, normalise_url


@pytest.mark.parametrize(
    ("source_type", "url", "expected"),
    [
        ("postgres", "postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgres", "postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgres", "postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("mysql", "mysql://u:p@h/db", "mysql+pymysql://u:p@h/db"),
        ("mysql", "mariadb://u:p@h/db", "mysql+pymysql://u:p@h/db"),
        ("mysql", "mysql+pymysql://u:p@h/db", "mysql+pymysql://u:p@h/db"),
        ("duckdb", "duckdb:///warehouse.duckdb", "duckdb:///warehouse.duckdb"),
        ("sqlite", "sqlite:///demo.db", "sqlite:///demo.db"),
    ],
)
def test_normalise_url(source_type: str, url: str, expected: str) -> None:
    assert normalise_url(Source(type=source_type, url=url)) == expected  # type: ignore[arg-type]


def test_a_url_for_another_database_type_is_not_rewritten() -> None:
    source = Source(type="duckdb", url="postgresql://u:p@h/db")
    assert normalise_url(source) == "postgresql://u:p@h/db"


def test_install_hints_use_the_published_package_name() -> None:
    for hint in _INSTALL_HINTS.values():
        assert "ninegear" not in hint
    assert "9gear-sentinel[mysql]" in _INSTALL_HINTS["mysql"]
    assert "9gear-sentinel[duckdb]" in _INSTALL_HINTS["duckdb"]


def test_unknown_driver_is_reported_as_a_connector_error() -> None:
    source = Source(type="sqlite", url="nonsense+nodriver://x")
    with pytest.raises(ConnectorError, match="source 'bad'"):
        create_source_engine("bad", source)
