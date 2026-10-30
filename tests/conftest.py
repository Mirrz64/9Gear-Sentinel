import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sentinel.config import SentinelConfig, load_config

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def stamp(delta: timedelta) -> str:
    return (NOW - delta).strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture
def demo_db(tmp_path: Path) -> Path:
    """A small SQLite database: 'customers' is healthy, 'orders' has problems."""
    path = tmp_path / "demo.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE customers (id INTEGER, email TEXT, created_at TEXT);
        CREATE TABLE orders (order_id INTEGER, customer_id INTEGER, updated_at TEXT);
        CREATE TABLE empty_table (id INTEGER, updated_at TEXT);
        """
    )
    conn.executemany(
        "INSERT INTO customers VALUES (?, ?, ?)",
        [(i, f"c{i}@example.com", stamp(timedelta(minutes=i))) for i in range(1, 51)],
    )
    orders = [
        (i, None if i % 10 == 0 else i, stamp(timedelta(days=3, minutes=i))) for i in range(1, 101)
    ]
    orders += [(5, 5, stamp(timedelta(days=3))), (7, 7, stamp(timedelta(days=3)))]
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?)", orders)
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def make_config(tmp_path: Path, demo_db: Path) -> Callable[[str], SentinelConfig]:
    """Write a config whose 'tables:' section is the given YAML, and load it."""

    def build(tables_yaml: str) -> SentinelConfig:
        text = (
            "version: 1\n"
            "sources:\n"
            "  local:\n"
            "    type: sqlite\n"
            f"    url: sqlite:///{demo_db.as_posix()}\n"
            "tables:\n" + tables_yaml
        )
        path = tmp_path / "sentinel.yml"
        path.write_text(text, encoding="utf-8")
        return load_config(path, environ={})

    return build
