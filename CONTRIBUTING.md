# Contributing

Thanks for helping improve 9Gear Sentinel.

## Setup

```bash
git clone https://github.com/Mirrz64/9Gear-Sentinel.git
cd 9Gear-Sentinel
uv venv && source .venv/bin/activate      # Windows Git Bash: .venv/Scripts/activate
uv pip install -e ".[dev]"
```

## Before opening a pull request

```bash
ruff format . && ruff check . && mypy src && pytest
```

Postgres integration tests run when a database is available:

```bash
docker compose up -d
SENTINEL_TEST_PG_URL=postgresql+psycopg://sentinel:sentinel@localhost:5433/analytics pytest
```

## Conventions

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- New check types live in `src/sentinel/checks/`, one file each, registered in `registry.py`, with unit tests that don't need a database.
- Keep user-facing messages short and specific: what was measured and what the limit was.
