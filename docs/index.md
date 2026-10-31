# 9Gear Sentinel

![9Gear Sentinel](assets/logo-light.svg#only-light){ .sentinel-hero }
![9Gear Sentinel](assets/logo-dark.svg#only-dark){ .sentinel-hero }

Data quality checks for your warehouse, declared in YAML and run anywhere you can run a command.

Sentinel catches stale tables, sudden row-count drops, null spikes, duplicate keys and silent schema changes before your stakeholders do. Every check runs as SQL inside your own database, so your data never leaves it.

```bash
pip install "9gear-sentinel[postgres]"
sentinel init
sentinel run
```

## What you get

- **Nine check types**: freshness, row counts, row-count changes between runs, nulls, null rates, uniqueness, accepted values, schema drift and your own SQL.
- **One YAML file** next to your code, with secrets read from environment variables or a `.env` file.
- **History**: every run is stored, so checks can compare against the past and you can see trends.
- **Alerts that don't nag**: Slack or email once when a check breaks and once when it recovers, never on every run while it stays broken.
- **Runs anywhere**: exit codes for CI, a built-in scheduler, and a shareable HTML report.
- **No AI, no vendor lock-in, no data leaving your warehouse.**

## Where to next

- New here? Start with [Getting started](getting-started.md).
- Writing checks? See the [Checks reference](checks.md).
- Wiring it into a pipeline? See [Scheduling and CI](scheduling.md).

## Supported databases

Postgres and SQLite are supported and tested in v0.1. Snowflake and BigQuery configs are accepted and should work once you install their SQLAlchemy dialects (`snowflake-sqlalchemy`, `sqlalchemy-bigquery`), but they aren't tested yet; official support is planned for v0.2.
