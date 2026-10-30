from collections.abc import Callable
from pathlib import Path

import pytest

from sentinel.config import SentinelConfig
from sentinel.runner import run_checks
from sentinel.store import ResultStore, StoreError
from tests.conftest import NOW

MakeConfig = Callable[[str], SentinelConfig]

CHECKS = (
    "  - source: local\n    table: orders\n    checks:\n"
    "      - row_count: { min: 1 }\n"
    "      - unique: { columns: [order_id] }\n"
    "      - accepted_values: { column: order_id, values: [1] }\n"
)


def test_open_creates_folder_and_tables(tmp_path: Path) -> None:
    store = ResultStore.open(f"sqlite:///{(tmp_path / 'deep' / 'r.db').as_posix()}")
    try:
        assert (tmp_path / "deep" / "r.db").is_file()
        assert store.history() == []
    finally:
        store.close()


def test_invalid_url_raises_store_error() -> None:
    with pytest.raises(StoreError):
        ResultStore.open("not a url")


def test_save_and_read_back(tmp_path: Path, make_config: MakeConfig) -> None:
    store = ResultStore.open(f"sqlite:///{(tmp_path / 'r.db').as_posix()}")
    try:
        report = run_checks(make_config(CHECKS), now=NOW, previous=store.last_observed)
        store.save(report)

        rows = store.history()
        assert [row.label for row in rows] == [
            "accepted_values(order_id)",
            "unique(order_id)",
            "row_count",
        ]
        assert {row.status for row in rows} == {"PASS", "FAIL"}

        row_count_key = report.results[0].check_key
        assert store.last_observed(row_count_key) == 102
        assert store.last_observed("unknown-key") is None
    finally:
        store.close()


def test_history_filters_and_limit(tmp_path: Path, make_config: MakeConfig) -> None:
    store = ResultStore.open(f"sqlite:///{(tmp_path / 'r.db').as_posix()}")
    try:
        config = make_config(CHECKS)
        for _ in range(3):
            store.save(run_checks(config, now=NOW))

        assert len(store.history(limit=100)) == 9
        assert len(store.history(check_type="unique", limit=100)) == 3
        assert len(store.history(table="orders", limit=4)) == 4
        assert store.history(table="no_such_table") == []
    finally:
        store.close()


def test_last_observed_returns_newest(tmp_path: Path, make_config: MakeConfig) -> None:
    import sqlite3

    store = ResultStore.open(f"sqlite:///{(tmp_path / 'r.db').as_posix()}")
    try:
        config = make_config(CHECKS)
        store.save(run_checks(config, now=NOW))
        db_path = config.sources["local"].url.removeprefix("sqlite:///")
        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM orders WHERE order_id > 10")
        conn.commit()
        conn.close()
        report = run_checks(config, now=NOW)
        store.save(report)
        assert store.last_observed(report.results[0].check_key) == 12  # 10 ids + 2 duplicates
    finally:
        store.close()
