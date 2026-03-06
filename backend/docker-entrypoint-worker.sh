#!/bin/sh

# Pre-pull browsertrix-crawler image (best-effort, don't block startup)
docker pull webrecorder/browsertrix-crawler:latest 2>/dev/null || true

# Start the worker
exec python -m app.worker.cli
