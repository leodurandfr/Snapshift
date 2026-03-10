#!/bin/sh

# Pre-pull browsertrix-crawler image (best-effort, don't block startup)
docker pull webrecorder/browsertrix-crawler:latest 2>/dev/null || true

# Start the worker with auto-reload on code changes
# watchfiles (bundled with uvicorn[standard]) restarts the process
# when any file changes in the mounted volumes
exec watchfiles "python -m app.worker.cli" /app/app /app/behaviors
