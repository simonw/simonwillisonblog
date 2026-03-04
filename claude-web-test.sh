#!/bin/bash
set -e

# Change to project directory
cd "$(dirname "$0")"

# ---- Help ----
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    cat <<'USAGE'
Usage: ./claude-web-test.sh [OPTIONS] [TEST_LABELS...]

Run Django tests for simonwillisonblog. Setup (PostgreSQL, virtualenv,
migrations) is detected and performed automatically on first run.

Arguments are passed directly to Django's test runner.

Examples:
  ./claude-web-test.sh                     # Run all tests
  ./claude-web-test.sh blog                # Run tests for the blog app
  ./claude-web-test.sh blog.tests.BlogTests.test_homepage
                                           # Run a single test
  ./claude-web-test.sh -v3                 # Verbose output
  ./claude-web-test.sh --parallel          # Run tests in parallel

Options:
  -h, --help    Show this help message and exit

Any other options (e.g. -v2, --failfast, --parallel) are forwarded to
"python manage.py test".
USAGE
    exit 0
fi

# ---- Virtualenv setup ----
if [ ! -d ".venv312" ]; then
    echo "Creating virtual environment (.venv312) with Python 3.12..."
    uv venv --python 3.12 .venv312
fi

source .venv312/bin/activate

# Install / update dependencies (fast no-op when already satisfied)
uv pip install -r requirements.txt --quiet

# ---- PostgreSQL setup ----
if ! pg_isready -q 2>/dev/null; then
    echo "Starting PostgreSQL..."
    sudo service postgresql start
    # Wait until ready (up to 10 s)
    for i in $(seq 1 10); do
        pg_isready -q 2>/dev/null && break
        sleep 1
    done
fi

# Ensure postgres user has a known password (idempotent)
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';" 2>/dev/null || true

# Create test database if it doesn't exist (idempotent)
sudo -u postgres createdb test_db 2>/dev/null || true

export DATABASE_URL=postgres://postgres:postgres@localhost/test_db

# ---- Migrations ----
# Only run migrations when the database schema is out of date.
if ! python manage.py migrate --check --noinput >/dev/null 2>&1; then
    echo "Running migrations..."
    python manage.py migrate --noinput --verbosity 0
fi

# ---- Run tests ----
echo "Running tests..."
exec python manage.py test "$@"
