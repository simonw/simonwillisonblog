# Simon Willison's Blog

Django 6.0 web application for https://simonwillison.net/

## Running Tests

This project uses Django's built-in test framework with PostgreSQL.

### Prerequisites

1. Python 3.12+ (Django 6.0 requirement)
2. PostgreSQL database running
3. Dependencies installed: `pip install -r requirements.txt`

### Running Tests

Use `uv run` with the pinned requirements; do not create or activate a virtual environment manually. PostgreSQL must be running locally.

Run Django's system checks and all tracked tests:

```bash
just
```

Run pytest directly with an explicit database URL:

```bash
DATABASE_URL=postgres:///simonwillisonblog uv run --with-requirements requirements.txt pytest
```

Run tests with verbose output, for an app, or for a specific class or method:

```bash
just test -v
just test blog
just test feedstats
just test monthly
just test blog/tests.py::TestBlog
just test blog/tests.py::TestBlog::test_homepage
```

The pytest configuration reuses the test database. Pass `--create-db` after schema changes. Tests use fast password hashing and omit production static-file serving, so `collectstatic` is not needed. See [AGENTS.md](AGENTS.md) for the database and commit-callback fixtures to use when writing tests.

## Project Structure

- `blog/` - Main blog app (entries, blogmarks, quotations, notes, tags)
- `monthly/` - Newsletter functionality
- `feedstats/` - Feed subscriber statistics
- `redirects/` - URL redirect handling
- `config/` - Django settings and URL configuration
- `templates/` - HTML templates
- `static/` - Static assets

## Test Data

Tests use `factory-boy` for generating test data. Factories are defined in `blog/factories.py`.
