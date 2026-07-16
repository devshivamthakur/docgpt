# DocGPT Backend

## Local development

1. Create and activate a virtual environment
2. Install dependencies with `uv sync`
3. Start the stack with Docker Compose:
   `docker compose up --build`
4. Visit:
   - http://localhost:8000/health
   - http://localhost:8000/docs

## Database migrations

Migrations are managed with [Alembic](https://alembic.sqlalchemy.org/).

### Create a new migration

After changing a model, generate a new revision:

```shell
uv run alembic revision --autogenerate -m "description_of_change"
```

### Apply pending migrations

```shell
uv run alembic upgrade head
```

### Rollback one step

```shell
uv run alembic downgrade -1
```

### View migration history

```shell
uv run alembic history
```

> **Note:** The database URL is read from your `.env` file via `app.core.config.settings`. Make sure `DATABASE_URL` in `.env` points to a reachable Postgres instance (use `localhost` when running outside Docker, or the service name `db` when inside Docker).
