# CLI reference

Every command takes `--config` / `-c` (default `sentinel.yml`). Run `sentinel COMMAND --help` for details.

| Command | What it does |
| --- | --- |
| `sentinel init [DIR]` | Write a starter `sentinel.yml` and `.env.example`. `--force` overwrites. |
| `sentinel validate` | Check the config without connecting. `--skip-env` doesn't require `${VARS}`. |
| `sentinel test-connection` | Run `SELECT 1` against each source. `--source` / `-s` picks one. |
| `sentinel run` | Run checks, print results, save them, send alerts. |
| `sentinel history` | Show stored results, newest first. |
| `sentinel report` | Write the latest run as an HTML page. |
| `sentinel snapshot-schema` | Accept tables' current columns as the `schema_drift` baseline. |
| `sentinel test-alert` | Send a test message to every alert channel. |
| `sentinel watch` | Run on a cron schedule until stopped. |
| `sentinel --version` | Print the version. |

## sentinel run

| Option | Notes |
| --- | --- |
| `--source`, `-s` | Only this source (repeatable) |
| `--table`, `-t` | Only this table (repeatable) |
| `--check` | Only this check type (repeatable) |
| `--tag` | Only tables or checks with this tag (repeatable) |
| `--no-store` | Don't save results |
| `--no-alerts` | Don't send alerts |
| `--dry-run` | Print the SQL each check would run, then stop |
| `--format`, `-f` | `table` (default) for people, or `json` for scripts and CI |

With `--format json`, stdout holds a single JSON document and nothing else (warnings and the alert count go to stderr), so it can be piped straight into `jq`:

```bash
sentinel run --format json --no-store | jq '.results[] | select(.status == "FAIL") | .message'
```

The document has `status`, `exit_code`, `counts` (pass, fail, warn, error, skip) and a `results` list. Each result has `source`, `table`, `check`, `type`, `severity`, `status`, `observed`, `message` and `duration_ms`. Exit codes are the same as for the table format.

## sentinel history

| Option | Notes |
| --- | --- |
| `--table`, `-t` | Only this table |
| `--check` | Only this check type |
| `--limit`, `-n` | Number of rows (default 20) |

## sentinel report

| Option | Notes |
| --- | --- |
| `--out`, `-o` | Output file (default `sentinel-report.html`) |

## sentinel snapshot-schema

With no options it snapshots every table that has a `schema_drift` check. `--table` / `-t` picks specific tables, with or without such a check.

## sentinel watch

| Option | Notes |
| --- | --- |
| `--cron` | Schedule, overriding `schedule.cron` |
| `--no-store`, `--no-alerts` | As for `run` |
| `--max-runs` | Stop after this many runs |
