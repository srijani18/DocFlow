#!/bin/sh
# Container start command. Render's free instances have no pre-deploy step, so migrations
# run here on every start (overview §8). Alembic uses DATABASE_URL_DIRECT when set.
set -eu

python -m alembic upgrade head
exec python -m app
