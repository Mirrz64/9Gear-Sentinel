# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/), and versions follow [Semantic Versioning](https://semver.org/).

## [0.1.1] - 2026-10-31

### Added
- Failure messages show examples: `unique` lists the most repeated keys, `accepted_values` lists the unexpected values it found
- 9Gear Sentinel logo in the README, docs site and HTML report

### Changed
- `sentinel validate` uses proper plurals ("1 source, 1 table, 3 checks")
- `sentinel init` lists the next steps, including `sentinel test-connection`
- The starter config says which names to change and links to the checks reference

### Development
- CI also runs on Windows and macOS
- `.gitattributes` keeps line endings consistent across platforms

## [0.1.0] - 2026-10-30

First public release.

### Checks
- `freshness`, `row_count`, `row_count_change`, `not_null`, `null_rate`, `unique`, `accepted_values`, `schema_drift` and `custom_sql`
- Common options on every check: `severity`, `where`, `tags` and `name`

### Commands
- `init`, `validate`, `test-connection`, `run`, `history`, `report`, `snapshot-schema`, `test-alert` and `watch`
- `run` filters (`--source`, `--table`, `--check`, `--tag`), `--dry-run`, `--no-store` and `--no-alerts`
- Exit codes: 0 passed or warned, 1 failed, 2 couldn't run

### Configuration
- One YAML file with `${VAR}` and `${VAR:-default}` substitution and `.env` support
- Validation errors that name the file, line and field

### Results and alerts
- Results store in SQLite or Postgres, with stable check keys so thresholds can change without losing history
- Slack and email alerts that fire on change of state: once on failure, once on recovery
- Self-contained HTML report with each check's recent trend

### Databases
- Postgres and SQLite supported and tested
