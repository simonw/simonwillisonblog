# Repo Guidelines

## Running tests

Use `uv run` with the pinned requirements. Do not create or activate a virtual
environment manually.

Run the full test suite from the repository root:

```bash
DATABASE_URL=postgres:///simonwillisonblog uv run --with-requirements requirements.txt ./manage.py test --keepdb
```

`--keepdb` is optional, but it makes repeated test runs much faster. PostgreSQL
must be running locally; the expected database URL is also recorded in
`.claude/settings.json`.

To run a specific test class:

```bash
DATABASE_URL=postgres:///simonwillisonblog uv run --with-requirements requirements.txt ./manage.py test blog.tests.BlogTests --keepdb
```

To run a specific test method:

```bash
DATABASE_URL=postgres:///simonwillisonblog uv run --with-requirements requirements.txt ./manage.py test blog.tests.BlogTests.test_homepage --keepdb
```
