#!/bin/sh
set -e

echo "==> Running database migrations..."
python manage.py migrate --noinput

if [ "$COLLECT_STATIC" = "1" ] || [ "$COLLECT_STATIC" = "true" ]; then
    echo "==> Collecting static files..."
    python manage.py collectstatic --noinput
fi

echo "==> Starting Daphne ASGI server..."
exec "$@"
