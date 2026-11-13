# Repo Guidelines

## Running tests

Use `uv run` with the pinned requirements. Do not create or activate a virtual environment manually.

Run Django's system checks and the full pytest-django suite from the repository root:

```bash
just
```

To run pytest directly:

```bash
DATABASE_URL=postgres:///simonwillisonblog uv run --with-requirements requirements.txt pytest
```

PostgreSQL must be running locally. `pytest.ini` enables `--reuse-db`; pass `--create-db` after schema changes to rebuild the test database. The default test paths include all tracked apps with tests and exclude untracked experiments.

To run a specific test class or method:

```bash
just test blog/tests.py::TestBlog
just test blog/tests.py::TestBlog::test_homepage
just test -k test_homepage
```

## Writing tests

Use plain pytest functions or classes, native assertions, and the response assertions in `pytest_django.asserts`. Request the `db` fixture or mark database tests with `@pytest.mark.django_db` so each test rolls back instead of flushing the database. Keep pure function tests free of database fixtures. Fixtures that create rows should explicitly request `db`.

The session-scoped `fast_test_settings` fixture uses a fast password hasher, omits WhiteNoise middleware, and uses ordinary static-file URLs. These overrides apply only during tests; application tests do not need `collectstatic`. CI separately checks production static-file collection.

Search indexing uses `transaction.on_commit()`. Wrap writes in `with commit_callbacks():` when a test needs to query the resulting index; the fixture executes callbacks when that block exits, while respecting callbacks discarded by rolled-back savepoints. Do not globally mock `on_commit()` to run immediately. Use `@pytest.mark.django_db(transaction=True)` only when a test needs real commits; those tests still flush the database.
