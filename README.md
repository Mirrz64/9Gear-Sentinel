# 9Gear Sentinel

[![CI](https://github.com/Mirrz64/9Gear-Sentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/Mirrz64/9Gear-Sentinel/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ninegear-sentinel)](https://pypi.org/project/ninegear-sentinel/)
[![Python](https://img.shields.io/pypi/pyversions/ninegear-sentinel)](https://pypi.org/project/ninegear-sentinel/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

**Data quality checks for your warehouse, declared in YAML and run anywhere you can run a command.**

Sentinel catches stale tables, sudden row-count drops, null spikes, duplicate keys and silent schema changes before your stakeholders do. Every check runs as SQL inside your own database, so your data never leaves it.

![Sentinel running against a demo database](https://raw.githubusercontent.com/Mirrz64/9Gear-Sentinel/main/docs/assets/demo.gif)

## Why Sentinel

- **Ten minutes to the first alert.** `pip install`, one YAML file, done. No server, no UI to host.
- **Alerts that don't nag.** Slack or email once when a check breaks and once when it recovers, not every hour while it stays broken.
- **It remembers.** Every run is stored, so checks can catch a 40% overnight drop in rows, and you can see each check's recent trend.
- **Fits your pipeline.** Clear exit codes for CI and Airflow, a built-in scheduler, and a shareable HTML report.
- **Plain SQL you can read.** `--dry-run` shows exactly what will be sent to your database.

## Quickstart

```bash
pip install "ninegear-sentinel[postgres]"
sentinel init                 # writes sentinel.yml and .env.example
cp .env.example .env          # set WAREHOUSE_URL
sentinel test-connection
sentinel run
```

```yaml
tables:
  - source: warehouse
    table: analytics.orders
    checks:
      - freshness: { column: updated_at, max_age: 6h }
      - row_count_change: { max_drop_pct: 30 }
      - unique: { columns: [order_id] }
      - null_rate: { column: customer_id, max_pct: 1, severity: warn }
      - accepted_values:
          column: status
          values: [pending, paid, shipped, refunded]
      - schema_drift: {}
```

Want to see it first? The repo includes a demo database with deliberate problems:

```bash
git clone https://github.com/Mirrz64/9Gear-Sentinel.git && cd 9Gear-Sentinel
pip install -e ".[postgres]"
docker compose up -d
sentinel run -c examples/sentinel.yml
```

## Checks

| Check | Fails when |
| --- | --- |
| `freshness` | The newest timestamp is older than `max_age` |
| `row_count` | The row count is outside `min` / `max` |
| `row_count_change` | The count moved more than allowed since the last run |
| `not_null` | Any null appears in the column |
| `null_rate` | The share of nulls is above `max_pct` |
| `unique` | Any key value appears more than once |
| `accepted_values` | A value outside the list appears |
| `schema_drift` | A column is added, removed or retyped since the baseline |
| `custom_sql` | Your query returns any rows |

## Reports

`sentinel report` turns the latest run into one self-contained HTML page, with failures first and each check's recent history.

![HTML report](https://raw.githubusercontent.com/Mirrz64/9Gear-Sentinel/main/docs/assets/report.png)

## Documentation

Full docs: **[mirrz64.github.io/9Gear-Sentinel](https://mirrz64.github.io/9Gear-Sentinel/)**, covering configuration, every check, alerts, scheduling, CI recipes and the CLI.

## Supported databases

Postgres and SQLite are supported and tested. Snowflake and BigQuery are planned for v0.2.

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup.

## Licence

[Apache-2.0](LICENSE). Built by Miracle Osabuogbe at 9Gear Tech.
