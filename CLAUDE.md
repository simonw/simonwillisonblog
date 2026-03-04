# Simon Willison's Blog

Django 6.0 web application for https://simonwillison.net/

## Running Tests

Use the `./claude-web-test.sh` script to run tests. It automatically handles all setup: creating a Python 3.12 virtualenv (`.venv312`), installing dependencies, starting PostgreSQL, running migrations, and executing the tests.

Run all tests:

```bash
./claude-web-test.sh
```

Run tests for a specific app:

```bash
./claude-web-test.sh blog
```

Run a specific test class or method:

```bash
./claude-web-test.sh blog.tests.BlogTests
./claude-web-test.sh blog.tests.BlogTests.test_homepage
```

Any additional options are forwarded to `python manage.py test`:

```bash
./claude-web-test.sh -v3              # Verbose output
./claude-web-test.sh --failfast       # Stop on first failure
./claude-web-test.sh --parallel       # Run tests in parallel
```

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
