#!/bin/sh
# Container start command. Render's free instances have no pre-deploy step, so migrations
# run here on every start (overview §8), over the same DATABASE_URL as the app.
set -eu

python -m alembic upgrade head
exec python -m app
