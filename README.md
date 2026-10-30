# 9Gear Sentinel

Data quality checks for your warehouse, declared in YAML and run anywhere you can run a command.

Sentinel catches stale tables, sudden row-count drops, null spikes and silent schema changes before your stakeholders do. Checks run as SQL inside your own warehouse, so your data never leaves it.

> Status: early development. v0.1 is in progress.

## Quickstart

```bash
pip install ninegear-sentinel
sentinel init
cp .env.example .env        # then set WAREHOUSE_URL
sentinel validate
```

## Example

```yaml
tables:
  - source: warehouse
    table: analytics.orders
    checks:
      - freshness: { column: updated_at, max_age: 6h }
      - row_count: { min: 1 }
      - unique: { columns: [order_id] }
```

## Development

```bash
uv venv
source .venv/Scripts/activate     # Windows Git Bash; use .venv/bin/activate on macOS/Linux
uv pip install -e ".[dev]"
pytest
```

## Licence

Apache-2.0
