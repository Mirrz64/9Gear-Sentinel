"""Command-line interface for 9Gear Sentinel."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from sentinel import __version__
from sentinel.config import ConfigError, load_config

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

ConfigOption = Annotated[
    Path,
    typer.Option("--config", "-c", help="Path to the config file."),
]


def _template(name: str) -> str:
    return files("sentinel").joinpath("templates", name).read_text(encoding="utf-8")


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
    try:
        cfg = load_config(config, require_env=not skip_env)
    except ConfigError as exc:
        count = len(exc.issues)
        for issue in exc.issues:
            err_console.print(str(issue), markup=False, highlight=False, style="red")
        err_console.print(
            f"\n{count} problem{'s' if count != 1 else ''} found", markup=False, style="bold red"
        )
        raise typer.Exit(EXIT_CONFIG_PROBLEM) from None

    console.print(
        f"{config} is valid: {len(cfg.sources)} source(s), "
        f"{len(cfg.tables)} table(s), {cfg.check_count()} check(s)",
        markup=False,
        highlight=False,
        style="green",
    )


if __name__ == "__main__":
    app()
