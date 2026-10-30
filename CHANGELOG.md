# Changelog

## Unreleased

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
