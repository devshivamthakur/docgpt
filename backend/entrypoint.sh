#!/bin/bash
set -e

# Run database migrations
echo "Running database migrations..."
uv run alembic upgrade head

# Start the application
exec uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-exclude .venv
