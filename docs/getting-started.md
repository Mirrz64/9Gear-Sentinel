# Getting started

This takes about ten minutes, from install to your first alert.

## Install

Sentinel needs Python 3.11 or newer.

```bash
pip install "9gear-sentinel[postgres]"
sentinel --version
```

## Try the demo first (optional)

The repository includes a Postgres database in Docker with deliberate problems, so you can see every kind of result before pointing Sentinel at your own data.

```bash
git clone https://github.com/Mirrz64/9Gear-Sentinel.git
cd 9Gear-Sentinel
pip install -e ".[postgres]"
docker compose up -d
sentinel run -c examples/sentinel.yml
```

## Create a config

```bash
sentinel init
```

This writes `sentinel.yml` and `.env.example` in the current folder. Copy `.env.example` to `.env` and set your connection URL:

```bash
WAREHOUSE_URL=postgresql+psycopg://user:password@host:5432/analytics
```

Never commit `.env`. Sentinel reads it automatically from the folder the config is in.

## Describe your checks

Edit `sentinel.yml`. Each table lists the checks to run against it:

```yaml
version: 1

sources:
  warehouse:
    type: postgres
    url: ${WAREHOUSE_URL}

tables:
  - source: warehouse
    table: analytics.orders
    checks:
      - freshness: { column: updated_at, max_age: 6h }
      - row_count_change: { max_drop_pct: 30 }
      - unique: { columns: [order_id] }
      - null_rate: { column: customer_id, max_pct: 1, severity: warn }
```

Check it without touching the database, then confirm the connection:

```bash
sentinel validate
sentinel test-connection
```

Validation errors name the file, line and field, for example `sentinel.yml:14 tables[0].checks[1].freshness.max_age: invalid duration '6x'`.

## Run

```bash
sentinel run
```

You get a table of results and an exit code: 0 when everything passed or only warned, 1 when an error-severity check failed, and 2 when a check couldn't run. Results are saved, so `sentinel history` and `sentinel report` have something to show.

## Next steps

- Add [alerts](alerts.md) so problems come to you.
- Run on a schedule or in CI: see [Scheduling and CI](scheduling.md).
- Browse every option in the [Configuration](configuration.md) reference.
