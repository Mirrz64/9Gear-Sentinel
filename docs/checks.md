# Checks

Each check is one line under a table's `checks:` list, written as the check type followed by its options. Every check also accepts the [common options](configuration.md#options-every-check-accepts): `severity`, `where`, `tags` and `name`.

## freshness

Fails when the newest value in a timestamp or date column is older than `max_age`.

```yaml
- freshness: { column: updated_at, max_age: 6h }
```

| Option | Notes |
| --- | --- |
| `column` | A timestamp or date column. Values without a time zone are treated as UTC. |
| `max_age` | `30m`, `6h`, `1d`, `2w`, combinations like `1h30m`, or a number of seconds |

An empty table, or a column that is entirely null, fails.

## row_count

Fails when the number of rows is outside the bounds. Set at least one.

```yaml
- row_count: { min: 1, max: 5000000 }
```

## row_count_change

Compares the row count with the previous stored run and fails on a sudden drop or spike. Set at least one limit.

```yaml
- row_count_change: { max_drop_pct: 30, max_growth_pct: 200 }
```

The first run records a baseline and passes. Changing the limits keeps the history, because a check's identity is its table and columns, not its thresholds.

## not_null

Fails if any value in the column is null.

```yaml
- not_null: { column: customer_id }
```

## null_rate

Fails when the share of nulls in a column is above `max_pct` (0 to 100, default 0). An empty table passes.

```yaml
- null_rate: { column: customer_id, max_pct: 1, severity: warn }
```

## unique

Fails if any key value appears more than once. Rows where a key column is null are ignored; use `not_null` for those.

```yaml
- unique: { columns: [order_id] }
- unique: { columns: [order_id, line_number], name: order_line_key }
```

## accepted_values

Fails if any non-null value is outside the list.

```yaml
- accepted_values:
    column: status
    values: [pending, paid, shipped, refunded]
```

## schema_drift

Fails when a column is added, removed or changes type compared with the stored baseline.

```yaml
- schema_drift: {}
- schema_drift: { ignore_columns: [_loaded_at] }
```

The first run records the baseline. After an intended change, accept the new schema so the check passes again:

```bash
sentinel snapshot-schema
```

## custom_sql

Runs your query and fails if it returns any rows. `name` is required. `where` is ignored here; put filters in the SQL.

```yaml
- custom_sql:
    name: orders_without_customers
    sql: >
      select o.order_id
      from analytics.orders o
      left join analytics.customers c on c.id = o.customer_id
      where o.customer_id is not null and c.id is null
```

!!! tip
    Use `sentinel run --dry-run` to see the exact SQL every check will send, with values filled in.
