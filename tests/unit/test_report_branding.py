from collections.abc import Callable
from pathlib import Path

from sentinel.config import SentinelConfig
from sentinel.report import render_report
from sentinel.runner import run_checks
from sentinel.store import ResultStore
from tests.conftest import NOW

MakeConfig = Callable[[str], SentinelConfig]


def test_report_embeds_both_brand_icons(tmp_path: Path, make_config: MakeConfig) -> None:
    store = ResultStore.open(f"sqlite:///{(tmp_path / 'r.db').as_posix()}")
    try:
        config = make_config(
            "  - source: local\n    table: orders\n    checks:\n      - row_count: { min: 1 }\n"
        )
        store.save(run_checks(config, now=NOW))
        latest = store.latest_run()
    finally:
        store.close()
    assert latest is not None

    page = render_report(latest)
    assert page.count('src="data:image/svg+xml;base64,') == 2
    assert 'class="light"' in page and 'class="dark"' in page
    assert "http" not in page.split("<body>")[1].split("</header>")[0]  # nothing external
