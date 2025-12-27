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
