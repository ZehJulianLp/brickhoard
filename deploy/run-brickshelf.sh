#!/bin/sh
set -eu

APP_DIR=/home/srvmgr/brickshelf

exec "$APP_DIR/.venv/bin/gunicorn" \
    --chdir "$APP_DIR" \
    --bind 127.0.0.1:54709 \
    --workers 2 \
    --threads 4 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    run:app
