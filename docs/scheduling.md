# Scheduling and CI

`sentinel run` is a normal command with meaningful exit codes, so anything that can run a command can run Sentinel.

| Exit code | Meaning |
| --- | --- |
| 0 | Everything passed, or only warn-severity checks failed |
| 1 | At least one error-severity check failed |
| 2 | A check couldn't run, or the config or connection has a problem |

## Built-in scheduler

```bash
sentinel watch                        # uses schedule.cron from the config
sentinel watch --cron "*/15 * * * *"  # or set it here
```

`watch` runs every check on the schedule (local time) until you press Ctrl+C. It re-reads the config before each run, so edits apply without a restart, and a broken config skips one run instead of stopping the watcher.

Cron syntax is the usual five fields: minute, hour, day of month, month, day of week (0 or 7 is Sunday). It supports `*`, numbers, ranges (`1-5`), lists (`0,30`) and steps (`*/15`).

## cron (Linux/macOS)

```bash
0 * * * * cd /opt/checks && /opt/checks/.venv/bin/sentinel run >> sentinel.log 2>&1
```

## GitHub Actions

```yaml
name: Data quality
on:
  schedule:
    - cron: "0 * * * *"
  workflow_dispatch:

jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install "9gear-sentinel[postgres]"
      - run: sentinel run --no-store
        env:
          WAREHOUSE_URL: ${{ secrets.WAREHOUSE_URL }}
```

Because GitHub runners start empty every time, either use `--no-store` or point `store.url` at a Postgres database so history and alert state persist between runs.

## Airflow

```python
from airflow.operators.bash import BashOperator

data_quality = BashOperator(
    task_id="data_quality",
    bash_command="sentinel run -c /opt/airflow/checks/sentinel.yml",
)
```

A failing check fails the task, so downstream tasks don't run on bad data.

## Reports

```bash
sentinel report --out report.html
```

Writes the latest stored run as one self-contained HTML page, with failures first and each check's last ten results. Attach it to a ticket, publish it as a CI artifact or open it locally.
