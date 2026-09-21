# Capture API Simulator

The API this test task is built against. It is given as-is and is not modified by the frontend work.

```bash
uv sync
uv run capture-api serve        # http://localhost:8700, docs at /docs
uv run capture-api report       # how the client behaved
uv run capture-api doctor
```

From the repository root, `docker compose up -d --wait simulator` runs the same API in a container.

This file exists because `pyproject.toml` declares `readme = "README.md"` and the Dockerfile copies
it; it was missing from the delivered archive, which broke both `uv sync` and the image build.
