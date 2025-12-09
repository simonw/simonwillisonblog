# Simon Willison's Blog

Django 6.0 web application for https://simonwillison.net/

## Running Tests

This project uses Django's built-in test framework with PostgreSQL.

### Prerequisites

1. Python 3.13
2. PostgreSQL database running
3. Dependencies installed: `pip install -r requirements.txt`

### Database Setup

Set the `DATABASE_URL` environment variable:

```bash
export DATABASE_URL=postgres://postgres:@localhost/test_db
```

Run migrations before testing:

```bash
python manage.py migrate --noinput
```

### Running Tests

Run all tests:

```bash
python manage.py test
```

Run tests with verbose output:

```bash
python manage.py test -v3
```

Run tests for a specific app:

```bash
python manage.py test blog
python manage.py test feedstats
python manage.py test monthly
```

Run a specific test class or method:

```bash
python manage.py test blog.tests.BlogTests
python manage.py test blog.tests.BlogTests.test_homepage
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
