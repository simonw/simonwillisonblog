#!/bin/bash
set -e

# Script to run tests for the simonwillisonblog project
# Can be run multiple times without breaking

# Change to project directory
cd "$(dirname "$0")"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv --python 3.12 .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies (uv pip install is idempotent)
echo "Installing dependencies..."
uv pip install -r requirements.txt --quiet

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

# Run tests
echo "Running tests..."
python manage.py test "$@"
