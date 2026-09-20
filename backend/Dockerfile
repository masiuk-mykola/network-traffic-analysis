FROM python:3.13-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY README.md ./
COPY src ./src
RUN uv sync --locked --no-dev


FROM python:3.13-slim AS runtime

RUN useradd --system --create-home --uid 10001 capture_api

WORKDIR /app
COPY --from=build --chown=capture_api:capture_api /app /app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CAP_HOST=0.0.0.0 \
    CAP_PORT=8700

USER capture_api
EXPOSE 8700

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=6 \
    CMD ["python", "-c", "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('CAP_PORT', '8700') + '/v1/health', timeout=2).status == 200 else 1)"]

CMD ["capture_api", "serve"]
