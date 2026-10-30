# 9Gear Sentinel

Data quality checks for your warehouse, declared in YAML and run anywhere you can run a command.

Sentinel catches stale tables, sudden row-count drops, null spikes and silent schema changes before your stakeholders do. Checks run as SQL inside your own warehouse, so your data never leaves it.

> Status: early development. v0.1 is in progress.

## Try it in two minutes

You need Docker and Python 3.11+.

```bash
git clone https://github.com/Mirrz64/9Gear-Sentinel.git
cd 9Gear-Sentinel
pip install -e ".[postgres]"
docker compose up -d
sentinel run -c examples/sentinel.yml
```

The demo database has a healthy `customers` table and an `orders` table with deliberate problems, so you'll see passes, a warning and failures.

## Use it on your own warehouse

```bash
pip install "ninegear-sentinel[postgres]"
sentinel init
cp .env.example .env        # then set WAREHOUSE_URL
sentinel test-connection
sentinel run
```

## Checks

```yaml
tables:
  - source: warehouse
    table: analytics.orders
    checks:
      - freshness: { column: updated_at, max_age: 6h }
      - row_count: { min: 1 }
      - null_rate: { column: customer_id, max_pct: 1, severity: warn }
      - not_null: { column: order_id }
      - unique: { columns: [order_id] }
```

Every check also accepts `severity` (`warn` or `error`), `where` (a SQL filter) and `tags`.

## Exit codes

`sentinel run` exits 0 when everything passed or only warned, 1 when an error-severity check failed, and 2 when a check couldn't run (bad config, unreachable database, missing column). Use it to fail a CI job or an Airflow task.

## Development

```bash
uv venv
source .venv/Scripts/activate     # Windows Git Bash; use .venv/bin/activate on macOS/Linux
uv pip install -e ".[dev]"
pytest
```

Postgres integration tests run when `SENTINEL_TEST_PG_URL` is set:

```bash
docker compose up -d
SENTINEL_TEST_PG_URL=postgresql+psycopg://sentinel:sentinel@localhost:5433/analytics pytest
```

## Licence

Apache-2.0
