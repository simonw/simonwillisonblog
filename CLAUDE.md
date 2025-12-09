# Simon Willison's Blog

Django 6.0 web application for https://simonwillison.net/

## Running Tests

This project uses Django's built-in test framework with PostgreSQL.

### Prerequisites

1. Python 3.12+ (Django 6.0 requirement)
2. PostgreSQL database running
3. Dependencies installed: `pip install -r requirements.txt`

### Setting up Python 3.12 with uv

If your system doesn't have Python 3.12+, use `uv` to install it:

```bash
# Install Python 3.12
uv python install 3.12

# Create a virtual environment with Python 3.12
uv venv --python 3.12 .venv312

# Activate and install dependencies
source .venv312/bin/activate
uv pip install -r requirements.txt
```

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
