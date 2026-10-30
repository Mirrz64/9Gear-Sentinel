"""Command-line interface for 9Gear Sentinel."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text
from sqlalchemy.exc import SQLAlchemyError

from sentinel import __version__
from sentinel.config import ConfigError, SentinelConfig, load_config
from sentinel.connectors import ConnectorError, check_connection, create_source_engine, short_error
from sentinel.runner import RunReport, Selection, run_checks
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
        "\nNext: copy .env.example to .env, set WAREHOUSE_URL, "
        "edit the checks, then run `sentinel validate`.",
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
        f"{config} is valid: {len(cfg.sources)} source(s), "
        f"{len(cfg.tables)} table(s), {cfg.check_count()} check(s)",
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
) -> None:
    """Run checks, print the results and exit 0 (ok), 1 (failures) or 2 (setup problem)."""
    cfg = _load_or_exit(config)
    selection = Selection(
        sources=source or (),
        tables=table or (),
        check_types=check or (),
        tags=tag or (),
    )

    store: ResultStore | None = None
    if not no_store:
        try:
            store = ResultStore.open(cfg.store.url)
        except StoreError as exc:
            _warn(f"{exc}; results won't be saved")

    try:
        report = run_checks(cfg, selection, previous=store.last_observed if store else None)
        if not report.results:
            err_console.print("no checks matched the filters", markup=False, style="yellow")
            raise typer.Exit(EXIT_CONFIG_PROBLEM)
        _print_report(report)
        if store:
            try:
                store.save(report)
            except SQLAlchemyError as exc:
                _warn(f"could not save results: {short_error(exc)}")
    finally:
        if store:
            store.close()

    raise typer.Exit(report.exit_code)


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


def _warn(message: str) -> None:
    err_console.print(f"warning: {message}", markup=False, highlight=False, style="yellow")


def _print_history(rows: list[HistoryRow]) -> None:
    grid = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    grid.add_column("When (UTC)")
    grid.add_column("Status")
    grid.add_column("Table")
    grid.add_column("Check")
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
