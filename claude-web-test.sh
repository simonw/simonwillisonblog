#!/bin/bash
set -e

# Change to project directory
cd "$(dirname "$0")"

# ---- Help ----
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    cat <<'USAGE'
Usage: ./claude-web-test.sh [OPTIONS] [TEST_LABELS...]

Run pytest-django tests for simonwillisonblog. PostgreSQL setup is detected
and performed automatically; uv supplies the pinned Python dependencies.

Arguments are passed directly to pytest.

Examples:
  ./claude-web-test.sh                     # Run all tests
  ./claude-web-test.sh blog                # Run tests for the blog app
  ./claude-web-test.sh blog/tests.py::TestBlog::test_homepage
                                           # Run a single test
  ./claude-web-test.sh -vv                 # Verbose output
  ./claude-web-test.sh --create-db         # Rebuild after schema changes

Options:
  -h, --help    Show this help message and exit

Any other options (e.g. -k, -x, --durations=10) are forwarded to pytest.
USAGE
    exit 0
fi

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

# ---- Run checks and tests ----
# pytest-django creates and migrates its own test database.
uv run --with-requirements requirements.txt ./manage.py check
exec uv run --with-requirements requirements.txt pytest "$@"
