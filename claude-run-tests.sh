#!/bin/bash
set -e

# Script to run tests for the simonwillisonblog project
# Can be run multiple times without breaking

# Change to project directory
cd "$(dirname "$0")"

# Start PostgreSQL if not running
if ! pg_isready -q 2>/dev/null; then
    echo "Starting PostgreSQL..."
    sudo service postgresql start
    sleep 2
fi

# Set up postgres user password if needed (idempotent)
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';" 2>/dev/null || true

# Create test database if it doesn't exist (idempotent)
sudo -u postgres createdb test_db 2>/dev/null || true

# Set database URL
export DATABASE_URL=postgres://postgres:postgres@localhost/test_db

# Run Django system checks and pytest (pytest-django manages test migrations).
uv run --with-requirements requirements.txt ./manage.py check
exec uv run --with-requirements requirements.txt pytest "$@"
