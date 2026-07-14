#!/usr/bin/env bash
# Render start script
set -o errexit

PORT="${PORT:-8000}"
echo "Starting gunicorn on port $PORT"
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT}" --log-level info
