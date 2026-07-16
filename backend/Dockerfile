FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

RUN pip install --no-cache-dir uv

# ── Install dependencies (cached until pyproject.toml / uv.lock change) ──
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen

# ── Copy application source (cached separately from deps) ───────────────
COPY . .

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
