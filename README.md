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
sentinel history
```

Every run is saved to a local results store (`.sentinel/results.db` by default), so `sentinel history` shows how a table's checks have changed over time. Use `--no-store` to skip saving.

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
      - row_count_change: { max_drop_pct: 30 }
      - accepted_values:
          column: status
          values: [pending, paid, shipped, refunded]
      - custom_sql:
          name: orders_without_customers
          sql: >
            select o.order_id from analytics.orders o
            left join analytics.customers c on c.id = o.customer_id
            where c.id is null
```

| Check | Fails when |
| --- | --- |
| `freshness` | The newest timestamp is older than `max_age` |
| `row_count` | The row count is outside `min` / `max` |
| `row_count_change` | The count moved more than allowed since the last stored run |
| `not_null` | Any null appears in the column |
| `null_rate` | The share of nulls exceeds `max_pct` |
| `unique` | Any key value appears more than once |
| `accepted_values` | A value outside the list appears |
| `custom_sql` | Your query returns any rows |
| `schema_drift` | A column is added, removed or changes type since the baseline |

Every check also accepts `severity` (`warn` or `error`), `where` (a SQL filter) and `tags`.

## Schema drift

The first run records each table's columns as a baseline. After that, any added, removed or retyped column fails the check until you accept the change:

```bash
sentinel snapshot-schema            # accept the current schema as the new baseline
```

## Alerts

Sentinel alerts on changes of state: once when a check starts failing and once when it recovers, never on every run while something stays broken.

```yaml
alerts:
  notify_on: [fail, error, recovered]   # also: warn
  slack:
    webhook_url: ${SLACK_WEBHOOK_URL}
  email:
    smtp_host: smtp.example.com
    smtp_port: 587
    username: ${SMTP_USER}
    password: ${SMTP_PASSWORD}
    to: [data-team@example.com]
```

Check the setup with `sentinel test-alert`. Use `sentinel run --no-alerts` to run quietly.

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
