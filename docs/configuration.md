# Configuration

Everything lives in one YAML file, `sentinel.yml` by default. Pass another with `--config` or `-c`.

```yaml
version: 1

sources:            # where checks run
  warehouse:
    type: postgres
    url: ${WAREHOUSE_URL}

store:              # where results are saved (optional)
  url: sqlite:///.sentinel/results.db

alerts:             # who hears about problems (optional)
  notify_on: [fail, error, recovered]
  slack:
    webhook_url: ${SLACK_WEBHOOK_URL}

schedule:           # used by `sentinel watch` (optional)
  cron: "0 * * * *"

tables:             # what to check
  - source: warehouse
    table: analytics.orders
    tags: [core]
    checks:
      - freshness: { column: updated_at, max_age: 6h }
```

Unknown keys are rejected, so a typo like `max_agee` is reported instead of silently ignored.

## Secrets and environment variables

Any string value can contain `${NAME}` or `${NAME:-default}`. Values come from the environment, or from a `.env` file in the same folder as the config. Real environment variables win over `.env`.

If a variable is missing, Sentinel stops with an error naming the line. `sentinel validate --skip-env` checks the structure without needing secrets, which is useful in CI.

## sources

A map of names to connections. Tables refer to a source by name.

| Field | Required | Notes |
| --- | --- | --- |
| `type` | yes | `postgres`, `sqlite`, `snowflake` or `bigquery` (see [supported databases](index.md#supported-databases)) |
| `url` | yes | A SQLAlchemy URL. `postgresql://` URLs use the psycopg 3 driver automatically. |

## store

| Field | Default | Notes |
| --- | --- | --- |
| `url` | `sqlite:///.sentinel/results.db` | SQLite (path relative to where you run Sentinel) or Postgres. Tables are prefixed `sentinel_`, so a shared Postgres store won't clash with anything. |

## alerts

See [Alerts](alerts.md) for the full description.

| Field | Default | Notes |
| --- | --- | --- |
| `notify_on` | `[fail, error]` | Any of `fail`, `error`, `warn`, `recovered` |
| `slack.webhook_url` | | A Slack incoming webhook URL |
| `email.smtp_host` | | Required for email |
| `email.smtp_port` | `587` | Port 465 uses SSL; other ports use STARTTLS when `use_tls` is true |
| `email.username`, `email.password` | | Used to log in when both are set |
| `email.from_address` | the username | |
| `email.to` | | A list of addresses |
| `email.use_tls` | `true` | |

## schedule

| Field | Notes |
| --- | --- |
| `cron` | Five-field cron expression in local time, e.g. `"*/15 * * * *"`. Only used by `sentinel watch`. |

## tables

| Field | Required | Notes |
| --- | --- | --- |
| `source` | yes | A name from `sources` |
| `table` | yes | `schema.table`, or just `table` |
| `tags` | no | Used by `sentinel run --tag` |
| `checks` | yes | At least one; see [Checks](checks.md) |

## Options every check accepts

| Field | Default | Notes |
| --- | --- | --- |
| `severity` | `error` | `warn` failures show as WARN and don't change the exit code |
| `where` | | A SQL filter, e.g. `created_at > now() - interval '1 day'` |
| `tags` | | Used by `sentinel run --tag` |
| `name` | generated | A label for output and history, e.g. `unique(order_id)` by default |
