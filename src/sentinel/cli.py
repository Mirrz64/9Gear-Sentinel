"""Command-line interface for 9Gear Sentinel."""

from __future__ import annotations

import time
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text
from sqlalchemy.exc import SQLAlchemyError

from sentinel import __version__
from sentinel.alerts import compute_events, send_alerts, send_test_alert
from sentinel.alerts.dispatch import channels
from sentinel.checks.schema_drift import read_columns
from sentinel.config import ConfigError, SentinelConfig, load_config
from sentinel.connectors import ConnectorError, check_connection, create_source_engine, short_error
from sentinel.report import render_report
from sentinel.runner import RunReport, Selection, preview_sql, run_checks
from sentinel.scheduler import CronError, CronSchedule, watch_loop
from sentinel.store import HistoryRow, ResultStore, StoreError

app = typer.Typer(
    help="Data quality checks for your warehouse, declared in YAML.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console(soft_wrap=True)
err_console = Console(stderr=True, soft_wrap=True)

EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_CONFIG_PROBLEM = 2

STATUS_STYLES = {
    "PASS": "green",
    "FAIL": "bold red",
    "WARN": "yellow",
    "ERROR": "bold magenta",
    "SKIP": "dim",
}

ConfigOption = Annotated[
    Path,
    typer.Option("--config", "-c", help="Path to the config file."),
]


def _count(number: int, word: str) -> str:
    return f"{number} {word}" if number == 1 else f"{number} {word}s"


def _template(name: str) -> str:
    return files("sentinel").joinpath("templates", name).read_text(encoding="utf-8")


def _load_or_exit(config: Path, *, require_env: bool = True) -> SentinelConfig:
    try:
        return load_config(config, require_env=require_env)
    except ConfigError as exc:
        count = len(exc.issues)
        for issue in exc.issues:
            err_console.print(str(issue), markup=False, highlight=False, style="red")
        err_console.print(
            f"\n{count} problem{'s' if count != 1 else ''} found", markup=False, style="bold red"
        )
        raise typer.Exit(EXIT_CONFIG_PROBLEM) from None


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"sentinel {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Data quality checks for your warehouse, declared in YAML."""


@app.command()
def init(
    directory: Annotated[Path, typer.Argument(help="Folder to create the files in.")] = Path("."),
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing files.")] = False,
) -> None:
    """Create a starter sentinel.yml and .env.example."""
    directory.mkdir(parents=True, exist_ok=True)
    targets = {
        directory / "sentinel.yml": _template("sentinel.yml"),
        directory / ".env.example": _template("env.example"),
    }
    existing = [path for path in targets if path.exists()]
    if existing and not force:
        for path in existing:
            err_console.print(f"{path} already exists (use --force to overwrite)", markup=False)
        raise typer.Exit(EXIT_CONFIG_PROBLEM)

    for path, content in targets.items():
        path.write_text(content, encoding="utf-8")
        console.print(f"created {path}", markup=False, highlight=False)

    console.print(
        "\nNext steps:\n"
        "  1. copy .env.example to .env and set WAREHOUSE_URL\n"
        "  2. point the checks in sentinel.yml at one of your tables\n"
        "  3. sentinel validate\n"
        "  4. sentinel test-connection\n"
        "  5. sentinel run",
        markup=False,
        highlight=False,
    )


@app.command()
def validate(
    config: ConfigOption = Path("sentinel.yml"),
    skip_env: Annotated[
        bool,
        typer.Option("--skip-env", help="Don't require ${VARS} to be set (useful in CI)."),
    ] = False,
) -> None:
    """Check the config file without connecting to any database."""
    cfg = _load_or_exit(config, require_env=not skip_env)
    console.print(
        f"{config} is valid: {_count(len(cfg.sources), 'source')}, "
        f"{_count(len(cfg.tables), 'table')}, {_count(cfg.check_count(), 'check')}",
        markup=False,
        highlight=False,
        style="green",
    )


@app.command("test-connection")
def test_connection(
    config: ConfigOption = Path("sentinel.yml"),
    source: Annotated[
        list[str] | None, typer.Option("--source", "-s", help="Only test this source.")
    ] = None,
) -> None:
    """Open each source and run SELECT 1."""
    cfg = _load_or_exit(config)
    names = source or list(cfg.sources)
    unknown = [name for name in names if name not in cfg.sources]
    if unknown:
        err_console.print(f"unknown source(s): {', '.join(unknown)}", markup=False, style="red")
        raise typer.Exit(EXIT_CONFIG_PROBLEM)

    failed = 0
    for name in names:
        try:
            engine = create_source_engine(name, cfg.sources[name])
            try:
                check_connection(engine)
            finally:
                engine.dispose()
        except ConnectorError as exc:
            failed += 1
            err_console.print(f"FAIL  {exc}", markup=False, highlight=False, style="red")
        except SQLAlchemyError as exc:
            failed += 1
            err_console.print(
                f"FAIL  {name}: {short_error(exc)}", markup=False, highlight=False, style="red"
            )
        else:
            console.print(f"OK    {name}", markup=False, highlight=False, style="green")

    if failed:
        raise typer.Exit(EXIT_CONFIG_PROBLEM)


@app.command()
def run(
    config: ConfigOption = Path("sentinel.yml"),
    source: Annotated[
        list[str] | None, typer.Option("--source", "-s", help="Only this source.")
    ] = None,
    table: Annotated[
        list[str] | None, typer.Option("--table", "-t", help="Only this table.")
    ] = None,
    check: Annotated[
        list[str] | None, typer.Option("--check", help="Only this check type.")
    ] = None,
    tag: Annotated[
        list[str] | None, typer.Option("--tag", help="Only tables or checks with this tag.")
    ] = None,
    no_store: Annotated[
        bool, typer.Option("--no-store", help="Don't save results to the results store.")
    ] = False,
    no_alerts: Annotated[bool, typer.Option("--no-alerts", help="Don't send alerts.")] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print the SQL each check would run, then stop.")
    ] = False,
) -> None:
    """Run checks, print the results and exit 0 (ok), 1 (failures) or 2 (setup problem)."""
    cfg = _load_or_exit(config, require_env=not dry_run)
    selection = Selection(
        sources=source or (),
        tables=table or (),
        check_types=check or (),
        tags=tag or (),
    )

    if dry_run:
        previews = preview_sql(cfg, selection)
        if not previews:
            err_console.print("no checks matched the filters", markup=False, style="yellow")
            raise typer.Exit(EXIT_CONFIG_PROBLEM)
        for preview in previews:
            console.print(f"-- {preview.table}  {preview.label}", style="dim", markup=False)
            console.print(f"{preview.sql};\n", markup=False, highlight=False)
        return

    report = _execute(cfg, selection, no_store=no_store, no_alerts=no_alerts)
    if report is None:
        err_console.print("no checks matched the filters", markup=False, style="yellow")
        raise typer.Exit(EXIT_CONFIG_PROBLEM)
    raise typer.Exit(report.exit_code)


@app.command()
def watch(
    config: ConfigOption = Path("sentinel.yml"),
    cron: Annotated[
        str | None,
        typer.Option("--cron", help="Cron schedule, overriding schedule.cron in the config."),
    ] = None,
    no_store: Annotated[
        bool, typer.Option("--no-store", help="Don't save results to the results store.")
    ] = False,
    no_alerts: Annotated[bool, typer.Option("--no-alerts", help="Don't send alerts.")] = False,
    max_runs: Annotated[
        int | None, typer.Option("--max-runs", min=1, help="Stop after this many runs.")
    ] = None,
) -> None:
    """Run all checks on a cron schedule (local time) until stopped with Ctrl+C.

    The config is re-read before every run, so edits apply without a restart.
    """
    cfg = _load_or_exit(config)
    expression = cron or (cfg.schedule.cron if cfg.schedule else None)
    if not expression:
        err_console.print(
            "no schedule: add schedule.cron to the config or pass --cron",
            markup=False,
            style="red",
        )
        raise typer.Exit(EXIT_CONFIG_PROBLEM)
    try:
        schedule = CronSchedule.parse(expression)
    except CronError as exc:
        err_console.print(str(exc), markup=False, style="red")
        raise typer.Exit(EXIT_CONFIG_PROBLEM) from None

    def run_once() -> None:
        try:
            current = load_config(config)
        except ConfigError as exc:
            for issue in exc.issues:
                err_console.print(str(issue), markup=False, highlight=False, style="red")
            _warn("config has problems; skipping this run")
            return
        try:
            _execute(current, Selection(), no_store=no_store, no_alerts=no_alerts)
        except Exception as exc:  # keep watching even if one run blows up
            _warn(f"run failed: {exc}")

    def on_wait(due: datetime) -> None:
        console.print(
            f"next run at {due:%Y-%m-%d %H:%M}", markup=False, highlight=False, style="dim"
        )

    console.print(
        f"watching on '{expression}'. Press Ctrl+C to stop.", markup=False, highlight=False
    )
    try:
        watch_loop(schedule, run_once, on_wait=on_wait, now=_now, sleep=_sleep, max_runs=max_runs)
    except KeyboardInterrupt:
        console.print("\nstopped", markup=False)


def _now() -> datetime:
    return datetime.now().astimezone()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _execute(
    cfg: SentinelConfig,
    selection: Selection,
    *,
    no_store: bool,
    no_alerts: bool,
) -> RunReport | None:
    """One full run: checks, printed results, alerts and storage. None if nothing matched."""
    store: ResultStore | None = None
    if not no_store:
        try:
            store = ResultStore.open(cfg.store.url)
        except StoreError as exc:
            _warn(f"{exc}; results won't be saved")

    try:
        report = run_checks(
            cfg,
            selection,
            previous=store.last_observed if store else None,
            schema_baseline=store.latest_snapshot if store else None,
        )
        if not report.results:
            return None
        _print_report(report)
        if not no_alerts:
            _alert(cfg, report, store)
        if store:
            try:
                store.save(report)
            except SQLAlchemyError as exc:
                _warn(f"could not save results: {short_error(exc)}")
    finally:
        if store:
            store.close()
    return report


@app.command("report")
def report_command(
    config: ConfigOption = Path("sentinel.yml"),
    out: Annotated[Path, typer.Option("--out", "-o", help="Where to write the HTML file.")] = Path(
        "sentinel-report.html"
    ),
) -> None:
    """Write the latest stored run as a self-contained HTML report."""
    cfg = _load_or_exit(config, require_env=False)
    try:
        store = ResultStore.open(cfg.store.url)
    except StoreError as exc:
        err_console.print(str(exc), markup=False, style="red")
        raise typer.Exit(EXIT_CONFIG_PROBLEM) from None
    try:
        latest = store.latest_run()
    finally:
        store.close()

    if latest is None:
        err_console.print(
            "no runs stored yet; run `sentinel run` first", markup=False, style="yellow"
        )
        raise typer.Exit(EXIT_CONFIG_PROBLEM)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(latest), encoding="utf-8")
    console.print(f"wrote {out}", markup=False, highlight=False, style="green")


@app.command()
def history(
    config: ConfigOption = Path("sentinel.yml"),
    table: Annotated[str | None, typer.Option("--table", "-t", help="Only this table.")] = None,
    check: Annotated[str | None, typer.Option("--check", help="Only this check type.")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, help="How many rows.")] = 20,
) -> None:
    """Show recent check results from the results store, newest first."""
    cfg = _load_or_exit(config, require_env=False)
    try:
        store = ResultStore.open(cfg.store.url)
    except StoreError as exc:
        err_console.print(str(exc), markup=False, style="red")
        raise typer.Exit(EXIT_CONFIG_PROBLEM) from None

    try:
        rows = store.history(table=table, check_type=check, limit=limit)
    finally:
        store.close()

    if not rows:
        console.print("no results yet; run `sentinel run` first", markup=False, style="yellow")
        return
    _print_history(rows)


@app.command("snapshot-schema")
def snapshot_schema(
    config: ConfigOption = Path("sentinel.yml"),
    table: Annotated[
        list[str] | None, typer.Option("--table", "-t", help="Only this table.")
    ] = None,
) -> None:
    """Save each table's current columns as the schema_drift baseline.

    Run it to set a baseline, or after an intended schema change to accept it.
    """
    cfg = _load_or_exit(config)
    if table:
        targets = [spec for spec in cfg.tables if spec.table in table]
    else:
        targets = [
            spec for spec in cfg.tables if any(c.type == "schema_drift" for c in spec.checks)
        ]
    if not targets:
        err_console.print(
            "no tables to snapshot: add a schema_drift check or pass --table",
            markup=False,
            style="yellow",
        )
        raise typer.Exit(EXIT_CONFIG_PROBLEM)

    try:
        store = ResultStore.open(cfg.store.url)
    except StoreError as exc:
        err_console.print(str(exc), markup=False, style="red")
        raise typer.Exit(EXIT_CONFIG_PROBLEM) from None

    failed = 0
    try:
        for spec in targets:
            try:
                engine = create_source_engine(spec.source, cfg.sources[spec.source])
                try:
                    with engine.connect() as conn:
                        columns = read_columns(conn, spec.table)
                finally:
                    engine.dispose()
                if not columns:
                    raise ConnectorError(f"table {spec.table} has no columns or was not found")
                store.save_snapshot(spec.source, spec.table, columns)
            except (ConnectorError, SQLAlchemyError) as exc:
                failed += 1
                message = str(exc) if isinstance(exc, ConnectorError) else short_error(exc)
                err_console.print(
                    f"FAIL  {spec.table}: {message}", markup=False, highlight=False, style="red"
                )
            else:
                console.print(
                    f"OK    {spec.table} ({len(columns)} columns)",
                    markup=False,
                    highlight=False,
                    style="green",
                )
    finally:
        store.close()

    if failed:
        raise typer.Exit(EXIT_CONFIG_PROBLEM)


@app.command("test-alert")
def test_alert(config: ConfigOption = Path("sentinel.yml")) -> None:
    """Send a test message to every configured alert channel."""
    cfg = _load_or_exit(config)
    names = channels(cfg.alerts)
    if not names:
        err_console.print(
            "no alert channels configured (add alerts.slack or alerts.email)",
            markup=False,
            style="yellow",
        )
        raise typer.Exit(EXIT_CONFIG_PROBLEM)

    failures = send_test_alert(cfg.alerts)
    for failure in failures:
        err_console.print(f"FAIL  {failure}", markup=False, highlight=False, style="red")
    if failures:
        raise typer.Exit(EXIT_CONFIG_PROBLEM)
    console.print(
        f"test alert sent via {' and '.join(names)}", markup=False, highlight=False, style="green"
    )


def _alert(cfg: SentinelConfig, report: RunReport, store: ResultStore | None) -> None:
    """Send alerts for state changes since the last stored run."""
    if not channels(cfg.alerts):
        return

    def previous_status(key: str) -> str | None:
        if store is None:
            return None
        try:
            return store.last_status(key)
        except SQLAlchemyError:
            return None

    events = compute_events(report.results, previous_status, cfg.alerts.notify_on)
    if not events:
        return
    failures = send_alerts(cfg.alerts, events)
    for failure in failures:
        _warn(failure)
    if not failures:
        console.print(f"alerts: {len(events)} sent", markup=False, highlight=False, style="dim")


def _warn(message: str) -> None:
    err_console.print(f"warning: {message}", markup=False, highlight=False, style="yellow")


def _print_history(rows: list[HistoryRow]) -> None:
    grid = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    grid.add_column("When (UTC)", no_wrap=True)
    grid.add_column("Status", no_wrap=True)
    grid.add_column("Table", no_wrap=True)
    grid.add_column("Check", no_wrap=True)
    grid.add_column("Result", ratio=1)
    for row in rows:
        grid.add_row(
            Text(row.checked_at.strftime("%Y-%m-%d %H:%M")),
            Text(row.status, style=STATUS_STYLES.get(row.status, "")),
            Text(row.table_name),
            Text(row.label),
            Text(row.message),
        )
    console.print(grid)


def _print_report(report: RunReport) -> None:
    grid = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    grid.add_column("Status")
    grid.add_column("Table")
    grid.add_column("Check")
    grid.add_column("Result", ratio=1)
    grid.add_column("Time", justify="right")

    for result in report.results:
        grid.add_row(
            Text(result.status, style=STATUS_STYLES[result.status]),
            Text(result.table),
            Text(result.label),
            Text(result.message),
            Text(f"{result.duration_ms} ms" if result.outcome != "skipped" else ""),
        )

    console.print(grid)
    exit_style = {0: "green", 1: "bold red", 2: "bold magenta"}[report.exit_code]
    console.print(f"\n{report.summary()}", markup=False, highlight=False, style=exit_style)


if __name__ == "__main__":
    app()
