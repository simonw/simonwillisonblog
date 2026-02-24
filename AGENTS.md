# Repo Guidelines

## Running tests

1. Activate the virtual environment:

```bash
source .venv312/bin/activate
```

2. Run tests from the repository root with:

```bash
python manage.py test
```

The `DATABASE_URL` environment variable is configured in `.claude/settings.json` and the PostgreSQL setup is handled by the SessionStart hook.

To run a specific test class:

```bash
python manage.py test blog.tests.BlogTests
```

To run a specific test method:

```bash
python manage.py test blog.tests.BlogTests.test_homepage
```

## Cursor Cloud specific instructions

### Services

| Service | How to start |
|---------|-------------|
| PostgreSQL | `sudo service postgresql start` (must be running before Django) |
| Django dev server | `source .venv312/bin/activate && DATABASE_URL=postgres:///simonwillisonblog DJANGO_DEBUG=1 python manage.py runserver 0.0.0.0:8033` |

### Gotchas

- PostgreSQL must use **trust** authentication for local connections. The update script handles this via `pg_hba.conf` modification, but if you see `FATAL: role "ubuntu" does not exist`, run: `sudo -u postgres psql -c "CREATE ROLE ubuntu SUPERUSER LOGIN;"`
- The `DATABASE_URL` env var must be set to `postgres:///simonwillisonblog` for all Django commands. The `.claude/settings.json` sets this, but in Cursor Cloud you may need to export it manually.
- Run `python manage.py collectstatic --noinput` before starting the dev server to avoid the "No directory at: /workspace/staticfiles/" warning.
- Standard commands for lint, test, build are documented in `CLAUDE.md`.
