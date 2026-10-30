# Changelog

## Unreleased

### Week 3
- Results store: every run saved to SQLite (or Postgres) with each check's outcome and measured value
- `sentinel history` with `--table`, `--check` and `--limit`, and `sentinel run --no-store`
- Checks: `row_count_change`, `accepted_values`, `custom_sql`
- Stable check keys, so changing a threshold keeps a check's history
- Cleaner output: ages rounded to two units, percentages without trailing zeros, thousands separators

### Week 2
- `sentinel run` with a results table, filters (`--source`, `--table`, `--check`, `--tag`) and exit codes
- `sentinel test-connection`
- Checks: `freshness`, `row_count`, `not_null`, `null_rate`, `unique`
- Postgres and SQLite connectors built on SQLAlchemy
- Docker Compose demo database with seeded problems
- Postgres integration tests in CI

### Week 1
- Config models for sources, store, alerts, schedule, tables and 9 check types
- YAML loader with ${VAR} and ${VAR:-default} substitution and .env support
- Validation errors that name the file, line and field
- `sentinel init`, `sentinel validate` and `sentinel --version`
